# Güneş Enerjisi Santralinde İnverter Üretim Tahmini

## Projenin amacı

Bu projede, bir güneş enerjisi santralindeki inverterin **15 dakika sonraki AC gücünü** tahmin etmek amaçlanmıştır. Böyle bir tahmin, üretimin kısa vadede nasıl değişebileceğini izlemek için kullanılabilir. Tahmin edilen değer enerji miktarı (`DAILY_YIELD`) değil, o andaki güç ölçümü (`AC_POWER`) değeridir.

## Veri ve hazırlık

[Solar Power Generation Data](https://www.kaggle.com/datasets/anikannal/solar-power-generation-data) veri setinin Plant 1 üretim ve hava sensörü dosyaları kullanılmıştır. Üretim dosyasında 22 inverter bulunur; bu çalışmada bir inverter seçilmiştir. Üretim ve hava ölçümleri aynı tarih ve saate göre eşleştirilmiştir. Her satıra tam 15 dakika sonraki AC güç değeri hedef olarak eklenmiştir. Karşılaştırma için 15 ve 30 dakika önceki ölçümler de hazırlanmıştır. Gerekli ölçümleri ve hedefi bulunan 3.122 örnek kalmıştır; bunlar 15 Mayıs–17 Haziran 2020 dönemindendir.

## Yöntem

Önce, “15 dakika sonraki güç şimdiki güçle aynı kalır” diyen basit bir tahmin oluşturulmuştur. Daha sonra Random Forest regresyon modeli eğitilmiştir. Modelin kullandığı bilgiler tahmin anında bilinen AC güç, güneş ışınımı, ortam sıcaklığı, panel sıcaklığı ve saattir. Geçmiş 15/30 dakika ölçümlerini de kullanan ikinci bir seçenek denenmiştir.

Veri zaman sırasıyla yaklaşık %60 öğrenme, %20 doğrulama ve %20 son test olarak ayrılmıştır. İki model seçeneği doğrulama verisinde karşılaştırılmış, daha iyi olan seçenek son testten önce belirlenmiştir. Son test verisi model seçimi için kullanılmamıştır. Başarı, gerçek ve tahmin edilen güç arasındaki **ortalama mutlak hata (MAE)** ile ölçülmüştür; bu değerin küçük olması daha iyidir.

## Sonuçlar

Doğrulama bölümünde yalnızca anlık ölçümleri kullanan modelin hatası **53,53**, geçmiş ölçümleri ekleyen modelin hatası **54,68** olmuştur. Bu nedenle anlık ölçümleri kullanan model seçilmiştir.

| Son test grubu | Basit tahmin MAE | Seçilen model MAE |
| --- | ---: | ---: |
| Tüm saatler, 624 örnek | 50,13 | **48,56** |
| Güneş ışınımı bulunan saatler | 90,15 | **87,32** |

Model basit tahminden daha düşük hata vermiştir, ancak fark sınırlıdır. Gece güç çoğunlukla sıfır olduğu için gündüz saatlerinin hatası ayrıca gösterilmiştir. [Son test gününün grafiği](figures/final_test_last_day.png), modelin günlük genel eğilimi izlediğini ve bazı ani yükseliş/düşüşleri kaçırdığını gösterir.

## Sınırlamalar

Veri yaklaşık 34 günlük bir dönemi kapsar ve yalnızca bir inverter üzerinde çalışılmıştır. Bu nedenle sonuçların başka mevsimlerde veya başka inverterlerde de aynı olacağı söylenemez. Hata değerleri veri setindeki `AC_POWER` ölçeğindedir; birim doğrulanmadan kW olarak yorumlanmamıştır. Çalışma, gelecekteki hava durumunu bilmeden, yalnızca tahmin anında mevcut ölçümleri kullanır.
