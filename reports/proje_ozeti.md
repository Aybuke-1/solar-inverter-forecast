# Güneş Enerjisi Santralinde İnverter Üretim Tahmini

## Projenin amacı

Bu projede bir güneş enerjisi santralindeki inverterlerin **15 dakika sonraki AC gücünü** tahmin etmek amaçlanmıştır. Tahmin edilen değer enerji miktarı (`DAILY_YIELD`) değil, o andaki güç ölçümü (`AC_POWER`) değeridir. Çalışma, kısa vadeli üretim değişimini izleme fikrine dayanır.

## Veri ve hazırlık

[Solar Power Generation Data](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data) veri setinin Plant 1 üretim ve hava sensörü dosyaları kullanılmıştır. Üretim dosyasında 22 inverter bulunur. Üretim ile güneş ışınımı ve sıcaklık ölçümleri aynı tarih ve saate göre eşleştirilmiştir. Her inverter kaydına **tam 15 dakika sonraki** AC güç değeri hedef olarak eklenmiştir. Gerekli ölçümleri ve hedefi bulunan **68.420 örnek** kalmıştır; veriler 15 Mayıs–17 Haziran 2020 dönemindendir.

## Yöntem

Önce, “15 dakika sonraki güç şimdiki güçle aynı kalır” diyen basit tahmin oluşturulmuştur. Ardından Random Forest ve Gradient Boosting regresyon modelleri denenmiştir. Model girdileri tahmin anında bilinen AC güç, güneş ışınımı, ortam sıcaklığı, panel sıcaklığı, saat/dakika ve inverter kimliğidir. Gelecekteki güç veya hava ölçümleri model girdisi olarak kullanılmamıştır.

Veri, **tüm inverterlerde aynı zaman sınırlarıyla**, yaklaşık %60 öğrenme, %20 doğrulama ve %20 son test olarak ayrılmıştır. Bir bölümdeki son kaydın hedefi sonraki bölüme düşüyorsa o kayıt çıkarılmıştır. Modeller doğrulama bölümünde karşılaştırılmış; son test yalnızca seçilen modelin değerlendirilmesinde kullanılmıştır. Hata ölçüsü **ortalama mutlak hata (MAE)** olup daha düşük değer daha iyi tahmin anlamına gelir.

## Sonuçlar

| Doğrulama yöntemi | MAE |
| --- | ---: |
| Basit tahmin | 66,45 |
| Random Forest | 60,49 |
| Gradient Boosting | **59,65** |

En düşük doğrulama hatasını Gradient Boosting verdiği için bu model seçilip öğrenme ve doğrulama verileriyle yeniden eğitilmiştir.

| Son test grubu | Basit tahmin MAE | Seçilen model MAE |
| --- | ---: | ---: |
| Tüm saatler, 13.860 örnek | 54,56 | **51,95** |
| Güneş ışınımı bulunan saatler, 7.766 örnek | 97,38 | **92,34** |
| Büyük güç değişimi olan kayıtlar, 1.174 örnek | 293,90 | **263,70** |

Model genel olarak basit tahminden daha düşük hata vermiştir. İnverter bazında bakıldığında **22 inverterin 20’sinde** hata azalmış, **2’sinde** artmıştır. [İnverter karşılaştırma grafiği](figures/inverter_improvement.png) ve [ayrıntılı CSV tablosu](inverter_errors.csv), bu farkları gösterir. Gece güç çoğunlukla sıfır olduğu için gündüz saatleri ayrıca değerlendirilmiştir.

“Büyük güç değişimi” eşiği, öğrenme verisindeki 15 dakikalık mutlak değişimlerin üst %10 sınırı olan **189,31** olarak belirlenmiştir. Son testte bu eşiği aşan 1.174 kayıt ayrı incelenmiştir. Bu kayıtların gelecekteki değişimi yalnızca sonuçları değerlendirmek için kullanılır; modele önceden verilmez. Model burada da basit tahminden iyi olsa da hata yüksek kalmıştır.

Her saatteki 22 inverter tahmini toplanarak **toplam inverter AC gücü** de değerlendirildi. Son testteki 630 zaman noktasında toplam güç MAE değeri basit tahminde **1.153,82**, modelde **1.098,33** oldu. [Son test gününün toplam güç grafiği](figures/plant_power_last_day.png) bu karşılaştırmayı gösterir. Toplam güç hataları tek inverter hatalarından farklı ölçektedir.

Sonuçları incelemek için [etkileşimli bir web ekranı](../dashboard/index.html) hazırlanmıştır. Bu ekran geçmiş test sonuçlarını gösterir; canlı üretim takibi yapmaz.

İlk aşamada tek inverter üzerinde yapılan deney [ayrı bir notta](ilk_deney.md) korunmuştur. Farklı veri bölme yöntemleri kullanıldığı için ilk deneyin sayısal sonuçları bu sonuçlarla doğrudan karşılaştırılmamalıdır.

## Sınırlamalar

Veri yaklaşık 34 günlük bir dönemi ve yalnızca bir santrali kapsar; farklı mevsim veya santrallerdeki başarı henüz ölçülmemiştir. İki inverterdeki olumsuz sonuç, tek bir modelin her cihaza eşit derecede uygun olmadığını gösterir. Hata değerleri veri setindeki `AC_POWER` ölçeğindedir; birim doğrulanmadan kW olarak yorumlanmamıştır.
