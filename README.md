# Güneş Enerjisi Santralinde İnverter Güç Tahmini

Bir güneş enerjisi santralindeki **22 inverterin 15 dakika sonraki AC gücünü** tahmin eden veri madenciliği projesi. Plant 1 üretim ve hava sensörü verileri birleştirilir; iki makine öğrenmesi modeli, “güç aynı kalır” diyen basit tahminle karşılaştırılır.

## Sonuç

Son test bölümünde (13.860 örnek) seçilen **Gradient Boosting** modelinin ortalama mutlak hatası **51,95**, basit tahminin hatası **54,56** oldu. Daha küçük hata daha iyi tahmin demektir. Güneş ışınımı bulunan saatlerde model **92,34**, basit tahmin **97,38** hata verdi. Gücün hızlı değiştiği 1.174 örnekte model **263,70**, basit tahmin **293,90** hata verdi. Model, 22 inverterin **20’sinde** basit tahminden daha iyiydi; 2’sinde daha kötüydü.

![Her inverterde modelin basit tahmine göre hata farkı](reports/figures/inverter_improvement.png)

Grafikte sağdaki yeşil çubuklar modelin daha iyi olduğu inverterleri, soldaki kırmızı çubuklar daha kötü olduğu inverterleri gösterir. İnverter başına sayılar [CSV tablosunda](reports/inverter_errors.csv), tüm deney ölçüleri [JSON dosyasında](reports/plant_metrics.json) bulunur. Ayrıntılı yöntem ve yorum için [proje özetine](reports/proje_ozeti.md) bakılabilir.

“Hızlı değişim” sınırı, öğrenme verisindeki 15 dakikalık mutlak güç değişimlerinin üst %10’undan hesaplandı (**189,31**). Bu grup yalnızca sonradan hata analizi için kullanılır; gerçekleşecek değişim modele önceden verilmez.

22 inverterin aynı saatteki tahminleri toplanarak **toplam inverter AC gücü** de incelendi. Son testte 630 zaman noktası için toplam güç MAE değeri basit tahminde **1.153,82**, modelde **1.098,33** oldu. Bu değerler 22 gücün toplamına ait olduğu için tek inverter hata değerleriyle aynı ölçekte değildir.

![Son test gününde toplam inverter AC gücü](reports/figures/plant_power_last_day.png)

## Kullanılan yöntem

1. Plant 1 içindeki 22 inverterin üretim kayıtları, aynı saatteki hava sensörü kayıtlarıyla eşleştirilir.
2. Her kayda **tam 15 dakika sonraki** `AC_POWER` değeri hedef olarak eklenir. Hedef değer model girdisi olarak kullanılmaz.
3. Anlık güç, ışınım, sıcaklık, saat ve inverter kimliği kullanılarak Random Forest ve Gradient Boosting modelleri denenir.
4. Veri **tarih ve saat bazında** yaklaşık %60 öğrenme, %20 doğrulama ve %20 son test olarak ayrılır. Böylece aynı saat farklı inverterlerde iki bölüme dağılmaz. Model seçimi yalnızca doğrulama verisiyle yapılır.
5. Seçilen model yeniden eğitilir; son testte hem genel hem de inverter bazındaki sonuçlar basit tahminle **ortalama mutlak hata (MAE)** üzerinden karşılaştırılır.

Doğrulama hataları: basit tahmin **66,45**, Random Forest **60,49**, Gradient Boosting **59,65**. Son model yalnızca tahmin anında bilinen ölçümleri kullanır; gelecek hava ölçümleri kullanılmaz.

## Kendi bilgisayarında çalıştırma

Python **3.14.8** ve Windows PowerShell ile çalıştırıldı. Proje klasöründe şu adımları uygula:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

[Kaggle veri setini](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data) indir. ZIP içindeki şu iki dosyayı `data/raw/` klasörüne koy:

- `Plant_1_Generation_Data.csv`
- `Plant_1_Weather_Sensor_Data.csv`

Ardından tüm santral deneyini çalıştır:

```powershell
.\.venv\Scripts\python.exe src\plant_model.py
```

Komut doğrulama ve test hatalarını terminale yazar; `reports/inverter_errors.csv`, `reports/plant_metrics.json` ve `reports/figures/` altındaki inverter/toplam güç grafiklerini oluşturur. Önceki tek inverter deneyini görmek istersen `src/train_model.py`, ilk veri kontrolü için `src/inspect_data.py` çalıştırabilirsin.

## Dosya yapısı

| Yol | İçerik |
| --- | --- |
| `src/plant_model.py` | 22 inverter için model karşılaştırma, test ve hata analizi |
| `src/train_model.py` | Tek inverterli ilk geliştirme deneyi |
| `src/inspect_data.py` | İlk veri incelemesi ve keşif deneyi |
| `data/raw/README.md` | Ham veriyi indirme yönergesi |
| `reports/proje_ozeti.md` | Ders için kısa yöntem ve sonuç anlatımı |
| `reports/inverter_errors.csv` | İnverter başına test hataları |
| `reports/plant_metrics.json` | Tekrar üretilebilir deney sonuçları |
| `reports/figures/` | Oluşturulan sonuç grafikleri |

Ham CSV dosyaları ve yerel Python ortamı `.gitignore` ile GitHub deposunun dışında tutulur.

## Kapsam ve sınırlamalar

Veri 15 Mayıs–17 Haziran 2020 döneminden ve yalnızca Plant 1 santralinden alınmıştır. Farklı mevsimler veya başka santraller için aynı başarı garanti edilemez. İki inverterde model basit tahminden daha kötü sonuç vermiştir; bu durum ayrı inceleme gerektirir. Tahmin edilen değişken enerji miktarı değil, `AC_POWER` güç ölçümüdür. Veri setindeki birim doğrulanmadığı için hata değerleri kW olarak adlandırılmaz.

Veri kaynağı: [Solar Power Generation Data](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data).
