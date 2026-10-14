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
| Gradient Boosting | **59,61** |

En düşük doğrulama hatasını Gradient Boosting verdiği için bu model seçilip öğrenme ve doğrulama verileriyle yeniden eğitilmiştir.

| Son test grubu | Basit tahmin MAE | Seçilen model MAE |
| --- | ---: | ---: |
| Tüm saatler, 13.860 örnek | 54,56 | **51,92** |
| Güneş ışınımı bulunan saatler, 7.766 örnek | 97,38 | **92,30** |
| Büyük güç değişimi olan kayıtlar, 1.174 örnek | 293,90 | **263,54** |

Model genel olarak basit tahminden daha düşük hata vermiştir. İnverter bazında bakıldığında **22 inverterin 20’sinde** hata azalmış, **2’sinde** artmıştır. [İnverter karşılaştırma grafiği](figures/inverter_improvement.png) ve [ayrıntılı CSV tablosu](inverter_errors.csv), bu farkları gösterir. Gece güç çoğunlukla sıfır olduğu için gündüz saatleri ayrıca değerlendirilmiştir.

“Büyük güç değişimi” eşiği, öğrenme verisindeki 15 dakikalık mutlak değişimlerin üst %10 sınırı olan **189,31** olarak belirlenmiştir. Son testte bu eşiği aşan 1.174 kayıt ayrı incelenmiştir. Bu kayıtların gelecekteki değişimi yalnızca sonuçları değerlendirmek için kullanılır; modele önceden verilmez. Model burada da basit tahminden iyi olsa da hata yüksek kalmıştır.

Her saatteki 22 inverter tahmini toplanarak **toplam inverter AC gücü** de değerlendirildi. Son testteki 630 zaman noktasında toplam güç MAE değeri basit tahminde **1.153,82**, modelde **1.097,90** oldu. [Son test gününün toplam güç grafiği](figures/plant_power_last_day.png) bu karşılaştırmayı gösterir. Toplam güç hataları tek inverter hatalarından farklı ölçektedir.

Sonuçları incelemek için [etkileşimli bir web ekranı](../dashboard/index.html) hazırlanmıştır. Bu ekran geçmiş test sonuçlarını gösterir; canlı üretim takibi yapmaz.

[Tahmin simülasyonu](../dashboard/simulation.html), son test gününün ardışık kayıtlarını adım adım gösterir. Önce mevcut güç ve 15 dakika sonrası model tahmini, sonraki adımda gerçek sonuç ve mutlak hata açılır. Bu, kayıtlı test verisinin oynatımıdır; canlı ölçüm bağlantısı veya tarayıcıda yeniden model eğitimi içermez. Negatif model tahminleri, fiziksel güç sınırına uygun olması için sıfıra çekilmiştir.

## Ek analizler ve operatör uyarısı

[Model analizi ekranında](../dashboard/analysis.html) son test hataları saat ve inverter bazında incelenebilir. 06.00–18.00 hedef saatlerinde modelin en yüksek saatlik MAE değeri **14.00'te 209,81** olmuştur; aynı saatte basit tahminin MAE değeri **196,69**'dur. [Saatlik hata grafiği](figures/hourly_errors.png) ve [inverter-saat tablosu](inverter_hourly_errors.csv), modelin hangi koşullarda zorlandığını gösterir. Genel başarı, bütün saatlerde daha iyi olduğu anlamına gelmez.

Model girdilerinin etkisi için seçilen model, yalnızca öğrenme verisinde eğitilmiş haliyle, **gündüz doğrulama kayıtlarında** değerlendirilmiştir. Her girdi grubu üç kez karıştırılıp hatadaki ortalama artış hesaplanmıştır. En yüksek artış güneş ışınımında **112,86**, anlık AC güçte **82,08** olmuştur. İnverter kimliğinin sayısal sütunları tek grup olarak karıştırılmıştır. [Girdi etkisi grafiği](figures/feature_importance.png) ve [tablosu](feature_importance.csv) tüm sonuçları içerir. Bağlantılı değişkenler nedeniyle bu sıralama kesin neden-sonuç açıklaması değildir.

Simülasyondaki “Büyük sapma” uyarısı, 22 inverterin toplam tahmin gücü ile gerçekleşen toplam güç arasındaki mutlak farka bakar. Uyarı eşiği, son test kullanılmadan, doğrulama dönemindeki toplam güç hatalarının **%95 sınırı olan 6.055,28** değeridir. Son testteki **630 zaman noktasının 29'unda**, son test gününün **4 noktasında** eşik aşılmıştır. Bu, operatörün inceleme yapması için bir işarettir; veri setinde arıza etiketi olmadığı için arıza teşhisi değildir. Toplam güç farkı ile tek inverter MAE değeri farklı ölçeklerdedir.

## Operasyon odaklı ek çalışma

[Operasyon masası](../dashboard/operations.html) üç ayrı çıktı sunar. **Ani düşüş modeli**, yalnızca gündüz ve geçmiş 15 dakika ölçümü mevcutken, her inverterin sonraki 15 dakikada büyük güç düşüşü yaşama riskini işaretler. Düşüş eşiği öğrenme verisindeki pozitif düşüşlerin %90 dilimi olan **278,48**'dir. Risk puanı için uyarı sınırı doğrulamada F1'e göre seçilmiştir. Son testte 7.744 gündüz örneğinin 385'inde gerçek sert düşüş vardı; 623 uyarının 186'sı isabetliydi (**precision %29,9**). Gerçek düşüşlerin **%48,3'ü** yakalandı (**recall**). Düşüşün son testteki taban oranı **%5,0** idi. [Precision–recall grafiği](figures/ramp_precision_recall.png) hatalı ve kaçırılan uyarıları değerlendirmeye yardım eder. Risk puanı kalibre edilmiş bir olasılık olarak sunulmaz.

**İnverter kıyas radarı**, her cihazın gücünü eğitim dönemindeki kendi %95 güç referansına böler ve aynı anda çalışan filonun medyanıyla karşılaştırır. Filo belirgin üretimdeyken medyanın %70'inin altında dört ardışık 15 dakikalık ölçüm kalan cihazlar kaydedilir. Son testte **14 Haziran 11.00–14.15** arasında iki inverterde **210 dakikalık** ortak ayrışma bulundu. [Olay grafiği](figures/peer_case.png) ve [bölüm tablosu](peer_episodes.csv) bu durumu gösterir. Kurulu kapasite ve arıza etiketleri bilinmediğinden neden çıkarılmaz.

**Operatör olay kaydı**, son testteki **29 büyük toplam güç sapmasını** ve eşzamanlı iki inverterlik **1 filo olayını** zaman sırasıyla saklar. Sapma kayıtlarında gerçekleşen/tahmin edilen toplam güç, en yüksek bireysel hatası olan inverterler ve tahmin anındaki ani düşüş uyarısı sayısı bulunur. [JSON kayıtları](operator_events.json) ve simülasyon sayfası üzerinden incelenebilir. Simülasyonda gerçek ölçüm zamanı gelmeden olay sonucu gösterilmez.

İlk aşamada tek inverter üzerinde yapılan deney [ayrı bir notta](ilk_deney.md) korunmuştur. Farklı veri bölme yöntemleri kullanıldığı için ilk deneyin sayısal sonuçları bu sonuçlarla doğrudan karşılaştırılmamalıdır.

## Sınırlamalar

Veri yaklaşık 34 günlük bir dönemi ve yalnızca bir santrali kapsar; farklı mevsim veya santrallerdeki başarı henüz ölçülmemiştir. İki inverterdeki olumsuz sonuç, tek bir modelin her cihaza eşit derecede uygun olmadığını gösterir. Hata değerleri veri setindeki `AC_POWER` ölçeğindedir; birim doğrulanmadan kW olarak yorumlanmamıştır.
