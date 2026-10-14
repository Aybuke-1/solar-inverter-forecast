"""Tahminin üstüne gündüz düşüş riski, filo kıyası ve olay kaydı ekle."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    precision_recall_fscore_support,
)


INPUTS = [
    "AC_POWER",
    "IRRADIATION",
    "AMBIENT_TEMPERATURE",
    "MODULE_TEMPERATURE",
    "HOUR",
    "MINUTE",
    "POWER_CHANGE_15",
    "IRRADIATION_CHANGE_15",
]
TARGET = "NEXT_AC_POWER"
PEER_RATIO_LIMIT = 0.70
PEER_MIN_FLEET_LEVEL = 0.25
PEER_MIN_INTERVALS = 4


def add_recent_changes(dataset: pd.DataFrame) -> pd.DataFrame:
    """Yalnızca gerçekten 15 dakika önceki mevcut ölçümü kullan."""
    data = dataset.copy()
    by_inverter = data.groupby("SOURCE_KEY")
    previous_time = by_inverter["DATE_TIME"].shift(1)
    consecutive = data["DATE_TIME"] - previous_time == pd.Timedelta(minutes=15)
    data["POWER_CHANGE_15"] = (
        data["AC_POWER"] - by_inverter["AC_POWER"].shift(1)
    ).where(consecutive)
    data["IRRADIATION_CHANGE_15"] = (
        data["IRRADIATION"] - by_inverter["IRRADIATION"].shift(1)
    ).where(consecutive)
    return data


def eligible_daytime(data: pd.DataFrame, indices: pd.Index) -> pd.DataFrame:
    subset = data.loc[indices]
    return subset[
        (subset["IRRADIATION"] > 0)
        & subset[["POWER_CHANGE_15", "IRRADIATION_CHANGE_15"]].notna().all(axis=1)
    ]


def train_ramp_risk(
    dataset: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    model_dir: Path | None = None,
) -> tuple[dict, pd.DataFrame]:
    """Gelecek 15 dakikadaki büyük güç düşüşünü ayrı bir modelle öngör."""
    data = add_recent_changes(dataset)
    train_day = eligible_daytime(data, train.index)
    validation_day = eligible_daytime(data, validation.index)
    test_day = eligible_daytime(data, test.index)
    features = pd.get_dummies(
        data[INPUTS + ["SOURCE_KEY"]], columns=["SOURCE_KEY"], dtype=int
    )

    positive_drops = train_day["AC_POWER"] - train_day[TARGET]
    drop_limit = float(positive_drops[positive_drops > 0].quantile(0.90))

    def labels(rows: pd.DataFrame) -> pd.Series:
        return ((rows["AC_POWER"] - rows[TARGET]) >= drop_limit).astype(int)

    def new_model() -> HistGradientBoostingClassifier:
        return HistGradientBoostingClassifier(
            max_iter=150,
            max_leaf_nodes=15,
            learning_rate=0.06,
            l2_regularization=1,
            random_state=42,
        )

    validation_model = new_model()
    validation_model.fit(features.loc[train_day.index], labels(train_day))
    validation_scores = validation_model.predict_proba(features.loc[validation_day.index])[:, 1]
    precision_curve, recall_curve, thresholds = precision_recall_curve(
        labels(validation_day), validation_scores
    )
    f1_curve = (
        2 * precision_curve[:-1] * recall_curve[:-1]
        / (precision_curve[:-1] + recall_curve[:-1] + 1e-12)
    )
    # Eşik yalnızca doğrulama bölümündeki F1 sonucuyla belirlenir.
    score_limit = float(thresholds[int(np.argmax(f1_curve))])

    final_model = new_model()
    training_day = pd.concat([train_day, validation_day])
    final_model.fit(features.loc[training_day.index], labels(training_day))
    if model_dir is not None:
        model_dir.mkdir(exist_ok=True)
        joblib.dump(
            {
                "model": final_model,
                "columns": features.columns.tolist(),
                "drop_limit": drop_limit,
                "risk_score_limit": score_limit,
            },
            model_dir / "risk_bundle.joblib",
        )
    test_scores = final_model.predict_proba(features.loc[test_day.index])[:, 1]
    test_labels = labels(test_day)
    test_flags = test_scores >= score_limit
    precision, recall, f1, _ = precision_recall_fscore_support(
        test_labels, test_flags, average="binary", zero_division=0
    )
    prevalence = float(test_labels.mean())
    metrics = {
        "drop_limit": drop_limit,
        "risk_score_limit": score_limit,
        "train_day_examples": int(len(train_day)),
        "validation_day_examples": int(len(validation_day)),
        "test_day_examples": int(len(test_day)),
        "test_drop_events": int(test_labels.sum()),
        "test_prevalence": prevalence,
        "test_average_precision": float(average_precision_score(test_labels, test_scores)),
        "test_precision": float(precision),
        "test_recall": float(recall),
        "test_f1": float(f1),
        "test_risk_alerts": int(test_flags.sum()),
        "test_correct_risk_alerts": int((test_flags & test_labels.to_numpy().astype(bool)).sum()),
        "precision_lift": float(precision / prevalence) if prevalence else 0.0,
    }
    predictions = test_day[["TARGET_TIME", "SOURCE_KEY", "AC_POWER", TARGET]].copy()
    predictions["risk_score"] = test_scores
    predictions["risk_alert"] = test_flags
    predictions["actual_drop"] = test_labels.to_numpy().astype(bool)
    return metrics, predictions


def calculate_peer_radar(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Her inverteri kendi eğitim dönemi tepe gücüne ve aynı andaki filoya göre kıyasla."""
    reference = train[train["IRRADIATION"] > 0].groupby("SOURCE_KEY")["AC_POWER"].quantile(0.95)
    if (reference <= 0).any():
        raise ValueError("Filo kıyası için her inverterin pozitif referans gücü gerekli.")
    radar = test[["TARGET_TIME", "SOURCE_KEY", TARGET]].copy()
    radar["normalized_power"] = radar[TARGET] / radar["SOURCE_KEY"].map(reference)
    fleet = radar.groupby("TARGET_TIME")["normalized_power"]
    radar["fleet_median"] = fleet.transform("median")
    radar["fleet_count"] = fleet.transform("size")
    radar["peer_ratio"] = radar["normalized_power"] / radar["fleet_median"].where(
        radar["fleet_median"] >= PEER_MIN_FLEET_LEVEL
    )
    radar["eligible"] = (
        (radar["fleet_median"] >= PEER_MIN_FLEET_LEVEL)
        & (radar["fleet_count"] >= 20)
    )
    radar["low_relative_power"] = radar["eligible"] & (radar["peer_ratio"] < PEER_RATIO_LIMIT)

    episode_rows = []
    for inverter, group in radar.sort_values("TARGET_TIME").groupby("SOURCE_KEY"):
        run = []
        for row in group.itertuples(index=False):
            consecutive = run and row.TARGET_TIME - run[-1].TARGET_TIME == pd.Timedelta(minutes=15)
            if row.low_relative_power:
                if run and not consecutive:
                    append_episode(inverter, run, episode_rows)
                    run = []
                run.append(row)
            elif run:
                append_episode(inverter, run, episode_rows)
                run = []
        if run:
            append_episode(inverter, run, episode_rows)

    episodes = pd.DataFrame(
        episode_rows,
        columns=["inverter", "start", "end", "intervals", "duration_minutes", "min_ratio"],
    )
    counts = episodes.groupby("inverter").size() if not episodes.empty else pd.Series(dtype=int)
    summary = radar.groupby("SOURCE_KEY").agg(
        eligible_points=("eligible", "sum"),
        low_points=("low_relative_power", "sum"),
        median_ratio=("peer_ratio", "median"),
        worst_ratio=("peer_ratio", "min"),
    ).reset_index()
    summary["episodes"] = summary["SOURCE_KEY"].map(counts).fillna(0).astype(int)
    summary = summary.sort_values(["episodes", "low_points", "SOURCE_KEY"], ascending=[False, False, True])
    return radar, summary, episodes


def append_episode(inverter: str, run: list, rows: list[dict]) -> None:
    if len(run) < PEER_MIN_INTERVALS:
        return
    rows.append(
        {
            "inverter": inverter,
            "start": run[0].TARGET_TIME,
            "end": run[-1].TARGET_TIME,
            "intervals": len(run),
            "duration_minutes": len(run) * 15,
            "min_ratio": float(min(row.peer_ratio for row in run)),
        }
    )


def build_priority(radar: pd.DataFrame, summary: pd.DataFrame, episodes: pd.DataFrame,
                   test: pd.DataFrame, report_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Uzun filo ayrışmalarını süreye göre inceleme sırasına koy; seçilebilir zaman çizgisi hazırla."""
    errors = test.assign(absolute_error=(test[TARGET] - test["MODEL_PREDICTION"]).abs())
    mae_by_inverter = errors.groupby("SOURCE_KEY")["absolute_error"].mean().to_dict()
    priority_rows = []
    series = {}
    last_day = radar["TARGET_TIME"].dt.date.max()
    for row in summary.itertuples(index=False):
        inverter = row.SOURCE_KEY
        own_episodes = episodes[episodes["inverter"] == inverter]
        total_minutes = int(own_episodes["duration_minutes"].sum())
        longest_minutes = int(own_episodes["duration_minutes"].max()) if not own_episodes.empty else 0
        if not own_episodes.empty:
            selected_day = own_episodes.sort_values(
                ["duration_minutes", "start"], ascending=[False, True]
            ).iloc[0]["start"].date()
        else:
            own_lows = radar[(radar["SOURCE_KEY"] == inverter) & radar["low_relative_power"]]
            counts = own_lows.groupby(own_lows["TARGET_TIME"].dt.date).size()
            selected_day = counts.idxmax() if not counts.empty else last_day
        status = "Öncelikli inceleme" if total_minutes else "İzle" if row.low_points else "Normal"
        priority_rows.append({
            "SOURCE_KEY": inverter, "priority": status,
            "episodes": int(row.episodes), "episode_minutes": total_minutes,
            "longest_minutes": longest_minutes, "low_points": int(row.low_points),
            "eligible_points": int(row.eligible_points),
            "worst_ratio": float(row.worst_ratio) if pd.notna(row.worst_ratio) else np.nan,
            "model_mae": float(mae_by_inverter[inverter]),
            "chart_day": str(selected_day),
        })
        chosen = radar[
            (radar["SOURCE_KEY"] == inverter)
            & (radar["TARGET_TIME"].dt.date == selected_day)
            & radar["eligible"]
        ].sort_values("TARGET_TIME")
        series[inverter] = {
            "day": str(selected_day),
            "points": [
                {"time": item.TARGET_TIME.strftime("%H:%M"),
                 "ratio": round(float(item.peer_ratio), 3),
                 "low": bool(item.low_relative_power)}
                for item in chosen.itertuples(index=False) if pd.notna(item.peer_ratio)
            ],
        }
    priority = pd.DataFrame(priority_rows)
    order = {"Öncelikli inceleme": 0, "İzle": 1, "Normal": 2}
    priority["sort_key"] = priority["priority"].map(order)
    priority = priority.sort_values(
        ["sort_key", "episode_minutes", "low_points", "SOURCE_KEY"],
        ascending=[True, False, False, True],
    ).drop(columns="sort_key")
    priority.to_csv(report_dir / "inverter_priority.csv", index=False, float_format="%.3f")
    return priority, series


def make_events(
    test: pd.DataFrame,
    totals: pd.DataFrame,
    alert_threshold: float,
    risk: pd.DataFrame,
    episodes: pd.DataFrame,
) -> list[dict]:
    """Gerçekleşmiş büyük sapmaları ve uzun filo-kıyas olaylarını kaydet."""
    risk_counts = risk.groupby("TARGET_TIME")["risk_alert"].sum().to_dict()
    events = []
    for row in totals[totals["ABS_MODEL_ERROR"] > alert_threshold].itertuples(index=False):
        moment = row.TARGET_TIME
        group = test[test["TARGET_TIME"] == moment].copy()
        group["absolute_error"] = (group[TARGET] - group["MODEL_PREDICTION"]).abs()
        contributors = [
            {
                "id": item.SOURCE_KEY,
                "actual": round(float(item.NEXT_AC_POWER), 2),
                "forecast": round(float(item.MODEL_PREDICTION), 2),
            }
            for item in group.nlargest(3, "absolute_error").itertuples(index=False)
        ]
        events.append(
            {
                "type": "deviation",
                "time": moment.isoformat(),
                "actual": round(float(row.NEXT_AC_POWER), 2),
                "forecast": round(float(row.MODEL_PREDICTION), 2),
                "difference": round(float(row.NEXT_AC_POWER - row.MODEL_PREDICTION), 2),
                "risk_alerts_before": int(risk_counts.get(moment, 0)),
                "top_inverters": contributors,
            }
        )
    if not episodes.empty:
        for (start, end), group in episodes.groupby(["start", "end"]):
            events.append(
                {
                    "type": "peer",
                    "time": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_minutes": int(group["duration_minutes"].max()),
                    "inverters": group["inverter"].tolist(),
                    "min_ratio": round(float(group["min_ratio"].min()), 3),
                }
            )
    return sorted(events, key=lambda event: event["time"], reverse=True)


def save_risk_chart(predictions: pd.DataFrame, metrics: dict, figure_dir: Path) -> Path:
    """Az görülen düşüşleri yakalama kalitesini bir PR eğrisiyle göster."""
    precision, recall, _ = precision_recall_curve(
        predictions["actual_drop"], predictions["risk_score"]
    )
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(recall, precision, color="#e79b46", linewidth=2, label="Risk modeli")
    ax.axhline(metrics["test_prevalence"], color="#3a9d78", linestyle="--", label="Rastgele seçim düzeyi")
    ax.scatter([metrics["test_recall"]], [metrics["test_precision"]], color="#cf5757", s=60, label="Seçilen uyarı eşiği")
    ax.set(xlabel="Düşüşleri yakalama oranı (recall)", ylabel="Uyarı isabet oranı (precision)", title="Son testte ani düşüş uyarısı")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    figure_dir.mkdir(parents=True, exist_ok=True)
    path = figure_dir / "ramp_precision_recall.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def save_peer_case_chart(radar: pd.DataFrame, episodes: pd.DataFrame, figure_dir: Path) -> Path | None:
    """En uzun ortak düşük performans olayını filo medyanıyla yan yana çiz."""
    if episodes.empty:
        return None
    first = episodes.sort_values(["duration_minutes", "start"], ascending=[False, True]).iloc[0]
    related = episodes[(episodes["start"] == first["start"]) & (episodes["end"] == first["end"])]
    window = radar[
        radar["TARGET_TIME"].between(
            first["start"] - pd.Timedelta(hours=1),
            first["end"] + pd.Timedelta(hours=1),
        )
    ]
    fig, ax = plt.subplots(figsize=(11, 5))
    fleet = window.groupby("TARGET_TIME", as_index=False)["fleet_median"].first()
    ax.plot(fleet["TARGET_TIME"], fleet["fleet_median"], label="Filo medyanı", color="#3a9d78", linewidth=2.5)
    for row in related.itertuples(index=False):
        device = window[window["SOURCE_KEY"] == row.inverter]
        ax.plot(device["TARGET_TIME"], device["normalized_power"], label=row.inverter, linewidth=1.8)
    ax.axvspan(first["start"], first["end"], color="#e79b46", alpha=0.15, label="İnceleme aralığı")
    ax.set(
        xlabel="Ölçüm zamanı",
        ylabel="Eğitim dönemi referansına göre güç",
        title=f"{first['start']:%Y-%m-%d}: {len(related)} inverterin filo kıyasından ayrılması",
    )
    ax.legend()
    ax.grid(alpha=0.2)
    fig.autofmt_xdate()
    fig.tight_layout()
    figure_dir.mkdir(parents=True, exist_ok=True)
    path = figure_dir / "peer_case.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def build_operations(
    dataset: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    totals: pd.DataFrame,
    alert_threshold: float,
    project_dir: Path,
) -> dict:
    """Operasyon katmanının raporlarını ve çevrimdışı arayüz verisini üret."""
    report_dir = project_dir / "reports"
    dashboard_dir = project_dir / "dashboard"
    figure_dir = report_dir / "figures"
    risk_metrics, risk = train_ramp_risk(dataset, train, validation, test, project_dir / "models")
    radar, peer_summary, episodes = calculate_peer_radar(train, test)
    priority, priority_series = build_priority(radar, peer_summary, episodes, test, report_dir)
    events = make_events(test, totals, alert_threshold, risk, episodes)
    risk_chart = save_risk_chart(risk, risk_metrics, figure_dir)
    peer_chart = save_peer_case_chart(radar, episodes, figure_dir)

    risk.to_csv(report_dir / "ramp_risk_predictions.csv", index=False, float_format="%.4f")
    peer_summary.to_csv(report_dir / "peer_summary.csv", index=False, float_format="%.3f")
    episodes.to_csv(report_dir / "peer_episodes.csv", index=False, float_format="%.3f")
    (report_dir / "operator_events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metrics = {
        **risk_metrics,
        "peer_ratio_limit": PEER_RATIO_LIMIT,
        "peer_min_fleet_level": PEER_MIN_FLEET_LEVEL,
        "peer_min_intervals": PEER_MIN_INTERVALS,
        "peer_episodes": int(len(episodes)),
        "peer_inverters": int((peer_summary["episodes"] > 0).sum()),
        "operator_events": int(len(events)),
        "deviation_events": int(sum(event["type"] == "deviation" for event in events)),
        "peer_incidents": int(sum(event["type"] == "peer" for event in events)),
        "priority_inverters": int((priority["priority"] == "Öncelikli inceleme").sum()),
    }
    (report_dir / "operations_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    last_day = totals["TARGET_TIME"].dt.date.max()
    last_day_risk = risk[risk["TARGET_TIME"].dt.date == last_day]
    by_time = last_day_risk.groupby("TARGET_TIME").agg(
        flagged=("risk_alert", "sum"),
        examined=("risk_alert", "size"),
    ).reset_index()
    dashboard_data = {
        "metrics": metrics,
        "risk_by_time": [
            {"time": row.TARGET_TIME.strftime("%H:%M"), "flagged": int(row.flagged), "examined": int(row.examined)}
            for row in by_time.itertuples(index=False)
        ],
        "peer_summary": [
            {
                "id": row.SOURCE_KEY,
                "eligible_points": int(row.eligible_points),
                "low_points": int(row.low_points),
                "episodes": int(row.episodes),
                "median_ratio": round(float(row.median_ratio), 3),
            }
            for row in peer_summary.itertuples(index=False)
        ],
        "priority": [
            {"id": row.SOURCE_KEY, "status": row.priority,
             "episodes": int(row.episodes), "minutes": int(row.episode_minutes),
             "longest_minutes": int(row.longest_minutes), "low_points": int(row.low_points),
             "eligible_points": int(row.eligible_points), "worst_ratio": round(float(row.worst_ratio), 3)
             if pd.notna(row.worst_ratio) else None,
             "model_mae": round(float(row.model_mae), 2), "chart_day": row.chart_day}
            for row in priority.itertuples(index=False)
        ],
        "priority_series": priority_series,
        "peer_episodes": [
            {
                "id": row.inverter,
                "start": row.start.isoformat(),
                "end": row.end.isoformat(),
                "minutes": int(row.duration_minutes),
                "min_ratio": round(float(row.min_ratio), 3),
            }
            for row in episodes.itertuples(index=False)
        ],
        "events": events,
    }
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "operations_data.js").write_text(
        "window.operationsData = " + json.dumps(dashboard_data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print("Ani düşüş test uyarısı / isabet:", metrics["test_risk_alerts"], metrics["test_correct_risk_alerts"])
    print("Ani düşüş precision / recall:", round(metrics["test_precision"], 3), round(metrics["test_recall"], 3))
    print("Filo kıyası bölüm sayısı / inverter:", metrics["peer_episodes"], metrics["peer_inverters"])
    print("Operatör olay kaydı:", metrics["operator_events"])
    print("Risk değerlendirme grafiği:", risk_chart)
    if peer_chart:
        print("Filo kıyası olay grafiği:", peer_chart)
    return metrics
