  // Core role: Renders the interactive galaxy map as a flat-top hex grid with zoom-driven visibility layers (clusters → sectors → sector names).
  //
  // Zoom thresholds:
  //   scale ≥ 0.55 → cluster name labels appear
  //   scale ≥ 1.60 → sector sub-hexes appear within each cluster
  //   scale ≥ 2.80 → sector name labels appear

  // Axial (q,r) for every navigable cluster. Derived from qsna.eu/api/x4/map
  // (cross-referenced 2026-06-07). hexSize = 10 000 km, STEP_X = 15 000 km.
  // 127 clusters total across all DLCs including Timelines.
  const CLUSTER_POS = {
    // Vanilla / base game
    "cluster_01_macro":[0,0],"cluster_02_macro":[1,1],"cluster_03_macro":[2,0],
    "cluster_04_macro":[3,-3],"cluster_05_macro":[0,-1],"cluster_06_macro":[-2,1],
    "cluster_07_macro":[-7,6],"cluster_08_macro":[-1,6],"cluster_09_macro":[4,2],
    "cluster_10_macro":[5,-3],"cluster_11_macro":[-2,-3],"cluster_12_macro":[-4,-1],
    "cluster_13_macro":[-5,2],"cluster_14_macro":[-6,5],"cluster_15_macro":[6,1],
    "cluster_16_macro":[6,2],"cluster_17_macro":[5,3],"cluster_18_macro":[5,-1],
    "cluster_19_macro":[7,-4],"cluster_20_macro":[9,-6],"cluster_21_macro":[9,-7],
    "cluster_22_macro":[2,-4],"cluster_23_macro":[4,-7],"cluster_24_macro":[-3,-2],
    "cluster_25_macro":[-6,-1],"cluster_26_macro":[-8,1],"cluster_27_macro":[-10,7],
    "cluster_28_macro":[-11,7],"cluster_29_macro":[-4,6],"cluster_30_macro":[-6,7],
    "cluster_31_macro":[-8,10],"cluster_32_macro":[-4,8],"cluster_33_macro":[-5,9],
    "cluster_34_macro":[3,3],"cluster_35_macro":[-3,-4],"cluster_36_macro":[-4,-3],
    "cluster_37_macro":[3,-5],"cluster_38_macro":[2,-5],"cluster_39_macro":[2,-1],
    "cluster_40_macro":[-6,2],"cluster_41_macro":[-6,3],"cluster_42_macro":[8,-4],
    "cluster_43_macro":[8,-3],"cluster_44_macro":[0,6],"cluster_45_macro":[-1,7],
    "cluster_46_macro":[-6,8],"cluster_47_macro":[4,0],
    "cluster_48_macro":[-10,8],"cluster_49_macro":[-8,3],"cluster_50_macro":[10,-7],
    // Later base-game additions (v7+)
    "cluster_709_macro":[4,-8],"cluster_710_macro":[7,-9],"cluster_711_macro":[8,-8],
    "cluster_712_macro":[7,-7],"cluster_713_macro":[6,-5],"cluster_714_macro":[-4,-4],
    "cluster_715_macro":[-8,0],"cluster_720_macro":[-10,4],"cluster_721_macro":[-14,11],
    "cluster_722_macro":[-9,-1],"cluster_723_macro":[-2,-6],"cluster_724_macro":[-14,1],
    "cluster_725_macro":[-2,0],"cluster_730_macro":[-10,5],"cluster_740_macro":[-3,1],
    // Cradle of Humanity
    "cluster_100_macro":[-13,7],"cluster_101_macro":[-14,8],"cluster_102_macro":[-15,9],
    "cluster_104_macro":[-14,9],"cluster_106_macro":[-15,10],"cluster_107_macro":[-14,6],
    "cluster_108_macro":[-15,6],"cluster_109_macro":[-16,6],"cluster_110_macro":[-15,5],
    "cluster_111_macro":[-16,5],"cluster_112_macro":[-8,8],"cluster_113_macro":[-11,1],
    "cluster_114_macro":[-12,1],"cluster_115_macro":[-13,2],"cluster_116_macro":[-17,5],
    // Split Vendetta
    "cluster_400_macro":[-7,12],"cluster_401_macro":[-3,9],"cluster_402_macro":[-3,10],
    "cluster_403_macro":[-8,12],"cluster_404_macro":[2,8],"cluster_405_macro":[3,7],
    "cluster_406_macro":[3,8],"cluster_407_macro":[8,2],"cluster_408_macro":[8,1],
    "cluster_409_macro":[10,1],"cluster_410_macro":[11,1],"cluster_411_macro":[12,2],
    "cluster_412_macro":[12,0],"cluster_413_macro":[13,0],"cluster_414_macro":[-3,11],
    "cluster_415_macro":[-2,11],"cluster_416_macro":[6,5],"cluster_417_macro":[5,7],
    "cluster_418_macro":[0,8],"cluster_419_macro":[2,6],"cluster_420_macro":[3,5],
    "cluster_421_macro":[8,3],"cluster_422_macro":[-9,13],"cluster_423_macro":[-11,14],
    "cluster_424_macro":[-12,15],"cluster_425_macro":[11,3],
    // Timelines
    "cluster_701_macro":[10,-4],"cluster_702_macro":[11,-5],"cluster_703_macro":[11,-6],
    "cluster_704_macro":[1,3],"cluster_705_macro":[-8,6],"cluster_706_macro":[-7,5],
    "cluster_708_macro":[-3,7],
    // Tides of Avarice (502/503 restored — no collision with corrected vanilla positions)
    "cluster_500_macro":[-1,2],"cluster_501_macro":[-2,4],"cluster_502_macro":[-3,4],
    "cluster_503_macro":[-3,3],"cluster_504_macro":[12,-2],
    // Kingdom End
    "cluster_601_macro":[-10,11],"cluster_602_macro":[-11,11],"cluster_603_macro":[-12,11],
    "cluster_604_macro":[-12,10],"cluster_605_macro":[-13,13],"cluster_606_macro":[-15,15],
    "cluster_607_macro":[-16,15],"cluster_608_macro":[-15,14],"cluster_609_macro":[-16,14],
  };

  // Real display names sourced from qsna.eu/api/x4/map.
  // Multiple macros share a name when they are sub-regions of the same star system.
  const CLUSTER_NAMES = {
    "cluster_01_macro":"Grand Exchange","cluster_02_macro":"Eighteen Billion",
    "cluster_03_macro":"Memory of Profit IX","cluster_04_macro":"Nopileos' Fortune",
    "cluster_05_macro":"Path to Profit","cluster_06_macro":"Black Hole Sun",
    "cluster_07_macro":"The Reach","cluster_08_macro":"Silent Witness I",
    "cluster_09_macro":"Bright Promise","cluster_10_macro":"Unholy Retribution",
    "cluster_11_macro":"Pontifex's Claim","cluster_12_macro":"True Sight",
    "cluster_13_macro":"Second Contact II Flashpoint","cluster_14_macro":"Argon Prime",
    "cluster_15_macro":"Ianamus Zura","cluster_16_macro":"Matrix #451",
    "cluster_17_macro":"Matrix #9","cluster_18_macro":"Trinity Sanctum III",
    "cluster_19_macro":"Hewa's Twin","cluster_20_macro":"Company Regard",
    "cluster_21_macro":"Scale Plate Green","cluster_22_macro":"Pious Mists II",
    "cluster_23_macro":"Sacred Relic","cluster_24_macro":"Holy Vision",
    "cluster_25_macro":"Faulty Logic","cluster_26_macro":"Atiya's Misfortune",
    "cluster_27_macro":"The Void","cluster_28_macro":"Antigone Memorial",
    "cluster_29_macro":"Hatikvah's Choice","cluster_30_macro":"Morning Star III",
    "cluster_31_macro":"Heretic's End","cluster_32_macro":"Tharka's Cascade",
    "cluster_33_macro":"Matrix #79B","cluster_34_macro":"Profit Center Alpha",
    "cluster_35_macro":"Lasting Vengeance","cluster_36_macro":"Cardinal's Redress",
    "cluster_37_macro":"Pious Mists IV","cluster_38_macro":"Pious Mists XI",
    "cluster_39_macro":"Memory of Profit X","cluster_40_macro":"Second Contact VII",
    "cluster_41_macro":"Second Contact XI","cluster_42_macro":"Hewa's Twin",
    "cluster_43_macro":"Hewa's Twin V","cluster_44_macro":"Silent Witness XI",
    "cluster_45_macro":"Silent Witness XII","cluster_46_macro":"Morning Star IV",
    "cluster_47_macro":"Trinity Sanctum VII","cluster_48_macro":"Getsu Fune",
    "cluster_49_macro":"Frontier Edge","cluster_50_macro":"Turquoise Sea",
    "cluster_709_macro":"Cardinal's Domain","cluster_710_macro":"Moo-Kye's Revenge",
    "cluster_711_macro":"Mi Ton's Refuge","cluster_712_macro":"Loomanckstrat's Legacy",
    "cluster_713_macro":"CEO's Doubt","cluster_714_macro":"Freedom's Reach",
    "cluster_715_macro":"Mists of Artemis","cluster_720_macro":"Ore Belt",
    "cluster_721_macro":"Adventure's Promise","cluster_722_macro":"Sanctum Verge",
    "cluster_723_macro":"Tempting Fumes","cluster_724_macro":"Circle of Deceit",
    "cluster_725_macro":"Void of Opportunity","cluster_730_macro":"Third Redemption",
    "cluster_740_macro":"Scarlet Star",
    "cluster_100_macro":"Asteroid Belt","cluster_101_macro":"Mars",
    "cluster_102_macro":"Venus","cluster_104_macro":"Sol (Earth)",
    "cluster_106_macro":"Mercury","cluster_107_macro":"Jupiter",
    "cluster_108_macro":"Sol (Saturn)","cluster_109_macro":"Uranus",
    "cluster_110_macro":"Neptune","cluster_111_macro":"Pluto",
    "cluster_112_macro":"Savage Spur","cluster_113_macro":"Segaris",
    "cluster_114_macro":"Gaian Prophecy","cluster_115_macro":"Brennan's Triumph",
    "cluster_116_macro":"Oort Cloud",
    "cluster_400_macro":"Wretched Skies IV Family Valka","cluster_401_macro":"Family Zhin",
    "cluster_402_macro":"Family Kritt","cluster_403_macro":"Wretched Skies V Family Phi",
    "cluster_404_macro":"Zyarth's Dominion I","cluster_405_macro":"Zyarth's Dominion IV",
    "cluster_406_macro":"Zyarth's Dominion X","cluster_407_macro":"Family Tkr",
    "cluster_408_macro":"Thuruk's Demise","cluster_409_macro":"Tharka's Ravine XXIV",
    "cluster_410_macro":"Tharka's Ravine XVI","cluster_411_macro":"Heart of Acrimony II",
    "cluster_412_macro":"Tharka's Ravine VIII",
    "cluster_413_macro":"Tharka's Ravine IV Tharka's Fall",
    "cluster_414_macro":"Rhy's Defiance","cluster_415_macro":"Matrix #598",
    "cluster_416_macro":"Guiding Star","cluster_417_macro":"Eleventh Hour",
    "cluster_418_macro":"Family Nhuut","cluster_419_macro":"Open Market",
    "cluster_420_macro":"Two Grand","cluster_421_macro":"Fires of Defeat",
    "cluster_422_macro":"Wretched Skies X","cluster_423_macro":"Litany of Fury",
    "cluster_424_macro":"Emperor's Pride",
    "cluster_425_macro":"Heart of Acrimony I The Boneyard",
    "cluster_500_macro":"Avarice","cluster_501_macro":"Windfall I Union Summit",
    "cluster_502_macro":"Windfall III The Hoard",
    "cluster_503_macro":"Windfall IV Aurora's Dream",
    "cluster_504_macro":"Unknown System",
    "cluster_601_macro":"Watchful Gaze","cluster_602_macro":"Barren Shores",
    "cluster_603_macro":"Great Reef","cluster_604_macro":"Ocean of Fantasy",
    "cluster_605_macro":"Sanctuary of Darkness","cluster_606_macro":"Kingdom End",
    "cluster_607_macro":"Rolk's Demise","cluster_608_macro":"Atreus' Clouds",
    "cluster_609_macro":"Menelaus' Oasis",
    "cluster_701_macro":"Mitsuno's Revelation","cluster_702_macro":"Mitsuno's Defiance",
    "cluster_703_macro":"Mitsuno's Sacrifice","cluster_704_macro":"President's End",
    "cluster_705_macro":"Nopileos' Memorial","cluster_706_macro":"Hatikvah's Faith",
    "cluster_708_macro":"Matrix #101",
  };

  // Jump gate positions within each sector, sourced from qsna.eu/api/x4/map (2026-06-07).
  // Format: sector_macro → [[abs_x_km, abs_z_km, target_cluster_num], ...]
  // abs_x/z are offset from sector center, scaled per cluster: ±300 km maps to
  // that cluster's sub-hex radius (which depends on its sector count).
  // Sectors with no gate data fall back to sub-hex center as line endpoint.
  const GATE_POS = {
    "cluster_01_sector001_macro":[[79,-25.34,4],[-191.49,34.01,5]],
    "cluster_01_sector002_macro":[[-117.97,-79.71,6]],
    "cluster_01_sector003_macro":[[19.08,80.48,2]],
    "cluster_02_sector001_macro":[[-47.5,-78.06,1],[116.27,55.85,3],[-46.86,80.93,8],[-152.98,12.7,501]],
    "cluster_03_sector001_macro":[[152.24,107.16,9],[-69.95,99.1,2],[-32.31,-42.87,39]],
    "cluster_04_sector002_macro":[[-42.45,176.45,22],[-62.01,178.28,1]],
    "cluster_05_sector001_macro":[[-15.64,94.91,1],[-133.53,-144.15,725]],
    "cluster_06_sector001_macro":[[-88.43,66.92,13],[19.49,164.81,503]],
    "cluster_06_sector002_macro":[[65.66,-145.47,725],[82.22,93.17,1]],
    "cluster_07_sector001_macro":[[210.8,-16.84,14]],
    "cluster_08_sector001_macro":[[27.58,103.26,44],[59.6,-15.42,34],[-162.16,-71.27,29],[-12.23,-152.37,2],[57.37,-173.01,704],[-114.75,-205.59,501]],
    "cluster_09_sector001_macro":[[-20,50,34],[-20,-75,18],[148.86,132.94,15],[-137.72,-10.42,3]],
    "cluster_10_sector001_macro":[[-73.27,8.11,22],[73.93,96.76,18]],
    "cluster_11_sector001_macro":[[-44.59,87.51,24],[46.5,87.74,22]],
    "cluster_12_sector001_macro":[[10,-90,24],[10,120,13]],
    "cluster_13_sector001_macro":[[-20,-65,12],[-72.4,-23.21,27],[-64.91,-88.1,40],[103.35,-86.34,6],[40,85,14]],
    "cluster_14_sector001_macro":[[50,-110,13],[-90.63,95.91,7],[-94.98,21.3,706],[50,120,29]],
    "cluster_15_sector001_macro":[[181.27,11.5,701],[47.57,102.66,16],[-135.72,152.26,9]],
    "cluster_15_sector002_macro":[[-129.62,83.13,408]],
    "cluster_16_sector001_macro":[[-121.32,107.13,17],[93.71,117.95,407],[-112.46,-129.66,15]],
    "cluster_17_sector001_macro":[[131.57,101.9,16],[137.87,176.73,421]],
    "cluster_18_sector001_macro":[[158.27,19.16,19],[3.21,35.16,9],[-13.78,45.69,47],[3.15,-143.68,10]],
    "cluster_19_sector001_macro":[[-122.47,103.21,18],[116.22,80.2,42]],
    "cluster_19_sector002_macro":[[140.09,-41.45,20]],
    "cluster_20_sector001_macro":[[-122.06,-112.87,21],[16.94,157.17,19],[113.88,7.53,50]],
    "cluster_21_sector001_macro":[[170.16,197.84,20]],
    "cluster_21_sector002_macro":[[165.75,138.97,50]],
    "cluster_22_sector001_macro":[[126.59,56.45,10],[136.32,2.31,37],[19.17,-119.92,23],[-17.64,-119.92,38],[-19.06,151.74,4],[-158.12,-56.83,11]],
    "cluster_23_sector001_macro":[[-1.35,146.09,22],[90.28,-59.74,709]],
    "cluster_24_sector001_macro":[[-29.31,58.17,12],[-100.61,-135.92,25],[115.29,-148.96,11],[112.01,-183.9,36],[120.45,179.39,725]],
    "cluster_25_sector001_macro":[[134.83,6.24,24]],
    "cluster_25_sector002_macro":[[-129.55,-117.23,26]],
    "cluster_26_sector001_macro":[[62.29,101.59,49]],
    "cluster_26_sector002_macro":[[116.12,-110.09,25],[84.64,-132.34,715]],
    "cluster_27_sector001_macro":[[-100.83,-76.21,28],[97.6,-67.13,13],[15.04,-194.5,49],[-14.11,297.49,48]],
    "cluster_28_sector001_macro":[[20.52,-152.82,113],[102.95,143.8,27]],
    "cluster_29_sector001_macro":[[-18.91,58.94,30],[182.53,227.65,32],[188.73,177.86,8],[-105.18,-128.63,14]],
    "cluster_30_sector001_macro":[[17.54,108.51,46],[-116.5,15.88,31],[107.87,-92.42,29]],
    "cluster_31_sector001_macro":[[-3.3,5.91,403],[-126.71,151.36,601],[133.71,-13.41,30]],
    "cluster_32_sector001_macro":[[132.62,86.61,708],[93.3,86.6,401],[72.04,-109.49,29]],
    "cluster_32_sector002_macro":[[-148.05,110.39,33]],
    "cluster_33_sector001_macro":[[-123.63,-54.4,112],[138.28,-115.63,32]],
    "cluster_34_sector001_macro":[[140.5,-75.24,9],[63.04,91.7,420],[-138.85,26.04,8]],
    "cluster_35_sector001_macro":[[-154.65,22.7,36]],
    "cluster_36_sector001_macro":[[-11.52,136.36,24],[41.41,-130.61,714],[114.36,-61.52,35]],
    "cluster_37_sector001_macro":[[-28.4,-102.67,38],[-36.27,121.11,22]],
    "cluster_38_sector001_macro":[[127.51,64.64,37],[-97.58,72.53,22]],
    "cluster_39_sector001_macro":[[119.22,-140.7,713],[-65.22,141.85,3]],
    "cluster_40_sector001_macro":[[129.77,88.01,13],[-93.73,147.64,41]],
    "cluster_41_sector001_macro":[[-35.76,-151.57,40]],
    "cluster_42_sector001_macro":[[-38.84,-107.25,19],[-1.87,142.17,43]],
    "cluster_43_sector001_macro":[[28.25,-138.64,42]],
    "cluster_44_sector001_macro":[[-38.83,142.85,45],[-102.27,-75.19,8]],
    "cluster_45_sector001_macro":[[127.46,-128.6,44]],
    "cluster_46_sector001_macro":[[-3.14,-176.81,30]],
    "cluster_47_sector001_macro":[[124.79,-76.73,18]],
    "cluster_48_sector001_macro":[[-39.19,-92.48,27],[-139.27,90.54,100],[-148.22,228.38,604],[215.01,107.8,112]],
    "cluster_49_sector001_macro":[[50,-110,26],[-52.63,73.23,720],[50,120,27]],
    "cluster_50_sector002_macro":[[-126.38,-141.37,21],[-78.53,121.96,20]],
    "cluster_709_sector001_macro":[[-122.9,69.88,723],[4.7,151.17,23],[169.89,120.55,710]],
    "cluster_710_sector001_macro":[[25.94,153.77,711],[-155.93,-155.89,709]],
    "cluster_711_sector001_macro":[[-163,74.18,712],[-88.58,-171.59,710]],
    "cluster_712_sector001_macro":[[-156.78,68.53,713],[127.94,-155.89,711]],
    "cluster_713_sector001_macro":[[-169.71,71.31,39],[76.54,-166.94,712]],
    "cluster_714_sector001_macro":[[11.69,156.13,36]],
    "cluster_715_sector001_macro":[[40.52,152.64,26]],
    "cluster_720_sector001_macro":[[0.87,156.98,730],[177.76,175.67,49],[145.99,-90.81,722],[-163.01,-87.5,721]],
    "cluster_721_sector001_macro":[[40.52,237.1,608],[145.99,-90.81,720]],
    "cluster_722_sector001_macro":[[-87.08,71.35,724],[40.52,152.64,720],[145.99,-90.81,723]],
    "cluster_723_sector001_macro":[[-87.08,71.35,722],[177.76,175.67,709]],
    "cluster_724_sector001_macro":[[40.52,152.64,115],[145.99,-125.97,722]],
    "cluster_725_sector001_macro":[[-100,55,740],[40.52,152.64,6],[177.76,37.27,5],[-1.64,-158.06,24]],
    "cluster_400_sector001_macro":[[-135.85,-66.27,403],[127.99,-35.32,401]],
    "cluster_401_sector001_macro":[[139.19,31.45,418],[-155.74,31.45,400],[-18.12,144.04,402],[79.56,-152.93,32]],
    "cluster_402_sector001_macro":[[-31.48,137.26,414],[81.59,-149.29,401]],
    "cluster_403_sector001_macro":[[-120.7,44.55,422],[171.29,81.27,400],[87.57,-157.54,31]],
    "cluster_404_sector001_macro":[[127.74,116.74,406],[-144.46,125.41,415],[20.14,-153.9,418]],
    "cluster_405_sector001_macro":[[57.35,84.81,406],[57.35,-160.02,419]],
    "cluster_406_sector001_macro":[[105.26,125.16,417],[-149.54,-126.75,404],[75.7,-167.66,405]],
    "cluster_407_sector001_macro":[[144.08,101.9,409],[-1.26,147.32,421],[-153.56,-98.21,16],[69.11,-170.21,408]],
    "cluster_408_sector001_macro":[[41.6,167.6,407],[-102.9,-97.7,15]],
    "cluster_409_sector001_macro":[[-146.52,142.74,421],[151.17,23.95,410],[-128.14,-117.21,407]],
    "cluster_410_sector001_macro":[[-153.58,-126.89,409],[-11.97,147.83,411],[109.38,-118.73,412]],
    "cluster_411_sector001_macro":[[0.27,122.31,425],[0.27,-117.21,410]],
    "cluster_412_sector001_macro":[[-154.17,121.84,410],[130.4,-10.3,413]],
    "cluster_413_sector001_macro":[[-138.88,-65.22,412]],
    "cluster_414_sector001_macro":[[163.4,133.58,415],[-18.59,-118.22,402]],
    "cluster_415_sector001_macro":[[-132.56,-116.07,414],[169.52,-19.37,404]],
    "cluster_416_sector001_macro":[[-136.33,-71.84,420]],
    "cluster_416_sector002_macro":[[1.62,137.8,417]],
    "cluster_417_sector001_macro":[[-144.39,99.49,406],[73.15,-159.51,416]],
    "cluster_418_sector001_macro":[[-170.85,11.65,401],[23.81,155.14,404],[152.88,-84.13,419]],
    "cluster_419_sector001_macro":[[-173.74,116.89,418],[-0.7,152.21,405],[124.76,-89.98,420]],
    "cluster_420_sector001_macro":[[-148.27,102.29,419],[82.19,154.37,416],[126.85,-72.23,421],[-121.76,-152.69,34]],
    "cluster_421_sector001_macro":[[-155,155.82,420],[-156.39,-54.66,17],[148.6,-46.73,409],[5.16,-166.25,407]],
    "cluster_422_sector001_macro":[[-173.74,33.28,423],[151.58,-123.16,403]],
    "cluster_423_sector001_macro":[[-155,119.06,424],[174.57,-10.09,422]],
    "cluster_424_sector001_macro":[[88.64,-118.09,423]],
    "cluster_425_sector001_macro":[[65.62,-162.49,411]],
    "cluster_100_sector001_macro":[[-11.52,136.36,101],[114.36,-61.52,48],[41.41,-130.61,107]],
    "cluster_101_sector001_macro":[[-132.5,131.85,102],[97.75,-150.66,100]],
    "cluster_102_sector001_macro":[[105.19,-85.7,101],[-67.26,152.73,106],[125.49,89.92,104]],
    "cluster_104_sector002_macro":[[-126.48,-125.89,102]],
    "cluster_106_sector001_macro":[[-17.18,-125.21,102]],
    "cluster_107_sector001_macro":[[131.87,127.11,100],[-67.51,-141.1,108]],
    "cluster_108_sector001_macro":[[64.42,128.75,107],[-78.81,-140.99,109]],
    "cluster_109_sector001_macro":[[125.38,-99.01,110],[138.36,151.05,108]],
    "cluster_110_sector001_macro":[[-126.68,-92.14,111],[-138.19,137.31,109],[156.45,11.39,115]],
    "cluster_111_sector001_macro":[[105.95,105.97,110],[-154.36,-137.82,116]],
    "cluster_112_sector001_macro":[[153.57,151.6,33]],
    "cluster_112_sector002_macro":[[-137.61,-62.73,48]],
    "cluster_113_sector001_macro":[[11.21,160.55,28],[-137.61,-62.73,114]],
    "cluster_114_sector001_macro":[[-139.51,29.03,115],[157.26,-85.19,113]],
    "cluster_115_sector001_macro":[[-137.61,-62.73,110],[141.46,-100.77,114],[3.77,-289.09,724]],
    "cluster_116_sector001_macro":[[31.97,155.35,111]],
    "cluster_500_sector003_macro":[[-152.88,64.8,502]],
    "cluster_501_sector001_macro":[[-0.57,139.49,8],[-138.21,-61.66,502],[129.6,-53.27,2]],
    "cluster_502_sector001_macro":[[134.98,-38.83,500],[118.4,143.35,501],[-26.39,-182.82,503]],
    "cluster_503_sector001_macro":[[8.12,193.18,502],[-64.89,-184.02,6]],
    "cluster_601_sector001_macro":[[169.89,120.55,31],[-155.93,-155.89,602]],
    "cluster_602_sector001_macro":[[-166.9,-111.84,603],[149.18,30.17,601]],
    "cluster_603_sector001_macro":[[26.85,149.37,605],[177.2,106.73,602],[-49.35,-159.14,604]],
    "cluster_604_sector001_macro":[[-12.42,159.94,603],[140.16,-150.07,48]],
    "cluster_605_sector001_macro":[[-87.38,98.68,606],[87.88,-116.98,603]],
    "cluster_606_sector002_macro":[[-148.03,-119.68,607]],
    "cluster_606_sector003_macro":[[147.76,-3.24,605]],
    "cluster_607_sector001_macro":[[59.17,155.44,606],[161.67,-9.79,608],[-85.56,-150.81,609]],
    "cluster_608_sector001_macro":[[-110.51,156.69,607],[-163.41,-105.78,609],[126.97,-150.89,721]],
    "cluster_609_sector001_macro":[[-65.61,186.39,607],[185.86,-30.02,608]],
    "cluster_701_sector001_macro":[[-155.93,48.1,15],[135.88,-141.02,702]],
    "cluster_702_sector001_macro":[[-155.93,43.23,701],[-1.91,-165.52,703]],
    "cluster_703_sector001_macro":[[-1.31,158.98,702]],
    "cluster_704_sector001_macro":[[-165.47,57.93,8]],
    "cluster_705_sector001_macro":[[162.71,-34.38,706]],
    "cluster_706_sector001_macro":[[-155.93,36.45,705],[162.71,30.11,14]],
    "cluster_708_sector001_macro":[[-155.93,11.01,32]],
    "cluster_730_sector001_macro":[[77.32,-151.95,720]],
    "cluster_740_sector001_macro":[[225,-25,725]],
  };

  // Sector sub-hex layouts within a cluster, indexed by sector count minus one.
  // Each entry is { r, offs }: `r` is the sub-hex radius and `offs` the centre
  // offsets, both as fractions of the drawn cluster hex radius. Sized so the
  // sectors FILL the cluster: a lone sector covers the whole cluster hex, and
  // multi-sector layouts are exact honeycomb fragments — sub-hexes share edges
  // with each other and their outer vertices land exactly on the cluster
  // boundary (flat-top axial geometry: edge-adjacent centres sit √3·r apart
  // along (±1.5r, ±(√3/2)r) or (0, ±√3·r)).
  const SECTOR_LAYOUTS = [
    { r: 1.000, offs: [[0, 0]] },
    // 2 sectors: each half-size hex is the cluster hex scaled by 0.5 toward an
    // opposite corner (upper-left / lower-right), so it nests flush against two
    // outline edges and the inner tips meet at the cluster centre.
    { r: 0.500, offs: [[-0.25, -0.433], [0.25, 0.433]] },
    { r: 0.500, offs: [[-0.5, 0], [0.25, -0.433], [0.25, 0.433]] },
    { r: 0.400, offs: [[-0.30, -0.5196], [-0.30, 0.1732], [0.30, -0.1732], [0.30, 0.5196]] },
    { r: 0.333, offs: [[0, 0], [-0.5, -0.2887], [0.5, -0.2887], [-0.5, 0.2887], [0.5, 0.2887]] },
    { r: 0.333, offs: [[0, -0.5774], [-0.5, -0.2887], [0.5, -0.2887], [-0.5, 0.2887], [0.5, 0.2887], [0, 0.5774]] },
  ];

  let _universeBuilt    = false;
  let _universeViewInited = false;
  let _universeTransform  = { x: 0, y: 0, scale: 1 };
  let _uTransformRaf    = 0;
  let _uPendingTransform = null;
  let _uCommitted   = null;
  let _uCommitTimer = 0;

  // ── Tilt ("almost 3D") constants ─────────────────────────────────────────
  // Applied to the DOM from here (not hardcoded in CSS) so the projection
  // maths below can never drift out of sync with what the GPU renders.
  // Set U_TILT_DEG to 0 to switch the whole effect off.
  const U_TILT_DEG   = 35;   // lean of the map plane, degrees
  const U_TILT_PERSP = 1200; // CSS perspective distance, px (smaller = deeper)
  const _uTiltSin = Math.sin(U_TILT_DEG * Math.PI / 180);
  const _uTiltCos = Math.cos(U_TILT_DEG * Math.PI / 180);

  // Flat map space (what _universeTransform works in) → on-screen position
  // after the tilt. rotateX about the wrap centre maps a flat point (u,v) to
  // (u, v·cos, v·sin) and CSS perspective then scales by d/(d−z); w is that
  // scale factor (≈ how "near" the point is — used as a label depth cue).
  function _uTiltProject(x, y, W, H) {
    const u = x - W / 2, v = y - H / 2;
    const w = U_TILT_PERSP / (U_TILT_PERSP - v * _uTiltSin);
    return { x: W / 2 + u * w, y: H / 2 + v * _uTiltCos * w, w };
  }

  // Inverse of _uTiltProject: cursor position → flat map space, so wheel-zoom
  // anchors exactly under the cursor and drags stay glued to the grab point.
  function _uTiltUnproject(X, Y, W, H) {
    const Yr = Y - H / 2;
    const v  = Yr * U_TILT_PERSP / (U_TILT_PERSP * _uTiltCos + Yr * _uTiltSin);
    const w  = U_TILT_PERSP / (U_TILT_PERSP - v * _uTiltSin);
    return { x: W / 2 + (X - W / 2) / w, y: H / 2 + v };
  }
  let _uLabelEls      = [];
  let _uSecLabelEls   = [];
  let _nearestStation = {}; // sector_macro → {name, jumps}
  let _sectorInfoMap  = {}; // sector_macro → sector row
  let _npcBySector    = {}; // sector_macro → [{owner_id, owner_name, count}]
  let _playerStaBySector = {}; // sector_macro → [station, …]
  let _playerShipsBySector = {}; // sector_macro → [ship, …]
  let _repByFaction      = {}; // faction_id → reputation row
  let _distFromEmpire    = {}; // sector_macro → jumps from empire
  let _sectorAdj      = {}; // sector_macro → [{macro, cost}]

  // Fit all clusters inside the map container, called on first tab open when
  // the element has real dimensions (deferred via requestAnimationFrame).
  function initUniverseView() {
    if (_universeViewInited) return;
    requestAnimationFrame(() => {
      const wrap = document.getElementById('universe-map-wrap');
      if (!wrap) return;
      const W = wrap.clientWidth  || window.innerWidth  - 200;
      const H = wrap.clientHeight || window.innerHeight - 150;
      const BASE_HEX = 48;
      const SQRT3    = Math.sqrt(3);
      const centers  = Object.values(CLUSTER_POS).map(([q, r]) => ({
        x:  BASE_HEX * 1.5 * q,
        y: -BASE_HEX * SQRT3 * (r + q * 0.5),
      }));
      const xs = centers.map(c => c.x);
      const ys = centers.map(c => c.y);
      const pad  = BASE_HEX * 2;
      const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad;
      const minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
      const scale = Math.min(W / (maxX - minX), H / (maxY - minY), 1.0) * 0.92;
      _universeTransform = {
        scale,
        x: W / 2 - ((minX + maxX) / 2) * scale,
        y: H / 2 - ((minY + maxY) / 2) * scale,
      };
      _uApplyTransform(_universeTransform);
      _universeViewInited = true;
    });
  }

  // Pan/zoom uses a gesture/commit split because browsers never GPU-composite
  // transforms on SVG content — changing the <g>'s transform re-rasterises all
  // ~1500 map nodes (incl. the u-neon blur groups) every frame, which measured
  // 30-110ms/frame vs the 16.7ms (60fps) budget. So while a gesture is active
  // we animate #universe-zoom-layer (an HTML div, which DOES composite) with
  // the *delta* from the last committed state, then once input goes quiet we
  // bake the full transform into the <g> attribute — one expensive repaint per
  // gesture instead of per frame. The map scales as a GPU texture mid-gesture
  // (labels grow/blur slightly) and snaps crisp on commit, like web map apps.
  function _uApplyTransform(t) {
    _uPendingTransform = { x: t.x, y: t.y, scale: t.scale };
    if (_uTransformRaf) return;

    _uTransformRaf = requestAnimationFrame(() => {
      _uTransformRaf = 0;
      const t = _uPendingTransform || _universeTransform;
      _uPendingTransform = null;

      const layer = document.getElementById('universe-zoom-layer');
      const vp    = document.getElementById('universe-viewport');
      if (!layer || !vp) return;

      // First call (initial fit) has no committed state yet — bake directly.
      if (!_uCommitted) { _uCommitTransform(t); return; }

      // Express t as a delta on top of the committed transform so the div's
      // CSS transform composes to exactly the same mapping as the <g> would:
      //   screen = ds·(committed·p) + (dx,dy)  ≡  t.scale·p + (t.x,t.y)
      // The overscan offset enters twice: the committed <g> transform has the
      // commit-time offset baked in (_uCommitted.ox/oy), and the layer's own
      // top-left sits at -offset relative to the wrap (read fresh in case the
      // window was resized mid-gesture). Both terms cancel to zero when ds=1.
      const ds = t.scale / _uCommitted.scale;
      const oxNow = -layer.offsetLeft;
      const oyNow = -layer.offsetTop;
      const dx = t.x - ds * (_uCommitted.x + _uCommitted.ox) + oxNow;
      const dy = t.y - ds * (_uCommitted.y + _uCommitted.oy) + oyNow;
      layer.style.transform = `translate(${dx}px,${dy}px) scale(${ds})`;

      // The flat label overlay can't follow per-frame gestures (it would need
      // a re-projection per label per frame), so it fades out until commit.
      document.getElementById('universe-labels')?.classList.add('u-gesturing');

      // Commit once the gesture has been quiet for a beat (wheel ticks and
      // drag moves keep pushing this back while the user is still going).
      clearTimeout(_uCommitTimer);
      _uCommitTimer = setTimeout(() => _uCommitTransform(_universeTransform), 180);
    });
  }

  // Bake the transform into the SVG <g> (the expensive full repaint) and reset
  // the gesture layer. Label sizing + zoom-level classes also live here so the
  // big style recalcs they trigger happen once per gesture, not per frame.
  function _uCommitTransform(t) {
    const layer = document.getElementById('universe-zoom-layer');
    const vp    = document.getElementById('universe-viewport');
    if (!layer || !vp) return;
    // The layer hangs 50% past the wrap on every side (overscan, see the CSS),
    // so the SVG's origin is offset from the wrap's. Baking that offset into
    // the <g> keeps _universeTransform itself wrap-relative — none of the
    // mouse/zoom math needs to know about overscan.
    const ox = -layer.offsetLeft;
    const oy = -layer.offsetTop;
    vp.setAttribute('transform', `translate(${t.x + ox},${t.y + oy}) scale(${t.scale})`);
    layer.style.transform = 'none';
    _uCommitted = { x: t.x, y: t.y, scale: t.scale, ox, oy };

    vp.classList.toggle('zoom-sectors', t.scale >= 1.60);

    // Reposition the crisp HTML labels: flat map position → tilt projection.
    // Runs once per gesture (not per frame), so looping every label is cheap.
    const labels = document.getElementById('universe-labels');
    if (labels) {
      const wrap = labels.parentElement;
      const W = wrap.clientWidth, H = wrap.clientHeight;
      labels.classList.remove('u-gesturing');
      labels.classList.toggle('show-clusters', t.scale >= 0.55);
      labels.classList.toggle('show-sectors',  t.scale >= 2.80);
      const place = ({ el, wx, wy }) => {
        const p = _uTiltProject(t.x + t.scale * wx, t.y + t.scale * wy, W, H);
        // w ≤ 0 means the point projects behind the camera (possible when far
        // off-screen at deep zoom) — park those out of sight instead of letting
        // the mirrored coordinates land somewhere visible.
        if (p.w <= 0.05 || p.x < -200 || p.x > W + 200 || p.y < -200 || p.y > H + 200) {
          el.style.transform = 'translate3d(-999.9rem,0,0)';
          return;
        }
        // scale(w) shrinks far labels and grows near ones — the depth cue that
        // makes flat text read as lying on the tilted plane.
        el.style.transform = `translate3d(${p.x.toFixed(1)}px,${p.y.toFixed(1)}px,0) scale(${p.w.toFixed(3)}) translate(-50%,-50%)`;
      };
      // Only the set that is actually visible at this zoom needs placing.
      if (t.scale >= 0.55 && t.scale < 2.80) _uLabelEls.forEach(place);
      if (t.scale >= 2.80) _uSecLabelEls.forEach(place);
    }
  }

  function renderUniverseMap(data) {
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const vp     = document.getElementById('universe-viewport');
    if (!vp) return;

    const BASE_HEX   = 48;
    // Sub-hexes are sized relative to the *drawn* cluster body (BASE_HEX - 1.5
    // inset) so a single-sector cluster's sub-hex exactly overlaps the cluster
    // outline instead of poking past it.
    const HEX_BODY   = BASE_HEX - 1.5;
    const SQRT3      = Math.sqrt(3);

    // Flat-top axial → pixel center. Y is negated so the galaxy matches the
    // in-game orientation (+z up in game space, +y down in SVG).
    function hexCenter(q, r) {
      return { x: BASE_HEX * 1.5 * q, y: -BASE_HEX * SQRT3 * (r + q * 0.5) };
    }

    // Six corner points of a flat-top hex (angles 0°,60°,…,300°).
    function hexPoints(cx, cy, size) {
      let pts = '';
      for (let i = 0; i < 6; i++) {
        const a = Math.PI / 3 * i;
        pts += `${cx + size * Math.cos(a)},${cy + size * Math.sin(a)} `;
      }
      return pts.trim();
    }

    function el(tag, attrs) {
      const e = document.createElementNS(SVG_NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
      return e;
    }

    // ── Build cluster metadata from sector data ───────────────────────────────
    const clusterInfo = {}; // macro → { name, owners:{id→count}, sectors[], anyDiscovered }
    (data.sectors || []).forEach(s => {
      if (!s.cluster_macro) return;
      const ci = clusterInfo[s.cluster_macro] ||
                 (clusterInfo[s.cluster_macro] = { name: null, owners: {}, sectors: [], anyDiscovered: false });
      ci.sectors.push(s);
      if (s.is_discovered) ci.anyDiscovered = true;
      // Fog-of-war: only DISCOVERED sectors contribute to the cluster's
      // dominant-faction colour — you don't know who owns space you haven't
      // explored. A cluster with no discovered sectors falls through to gray.
      if (s.owner_id && s.is_discovered) ci.owners[s.owner_id] = (ci.owners[s.owner_id] || 0) + 1;
      // Use cluster_name only when it's a real display name, not the raw macro.
      if (s.cluster_name && s.cluster_name !== s.cluster_macro && !ci.name)
        ci.name = s.cluster_name;
    });

    function clusterDisplayName(macro) {
      // API names take priority; sector-data cluster_name may still be the raw macro.
      if (CLUSTER_NAMES[macro]) return CLUSTER_NAMES[macro];
      const ci = clusterInfo[macro];
      if (ci && ci.name) return ci.name;
      return macro.replace(/_macro$/, '').replace(/_/g, ' ')
                  .replace(/\b\w/g, c => c.toUpperCase());
    }

    function clusterColour(macro) {
      const ci = clusterInfo[macro];
      if (!ci || !Object.keys(ci.owners).length) return '#3d444d';
      const sorted = Object.entries(ci.owners).sort((a, b) => b[1] - a[1]);
      for (const [id] of sorted) {
        const col = FACTION_COLOURS[id];
        if (col) return col;
      }
      return '#3d444d';
    }

    const UNDISCOVERED_COLOUR = '#3d444d';

    // ── Render SVG ────────────────────────────────────────────────────────────
    vp.innerHTML = '';
    // Labels are HTML in the flat overlay, not SVG (see #universe-labels CSS).
    // Each entry stores the element plus its position in map world units so
    // _uCommitTransform can re-project it after every gesture.
    const labelsEl = document.getElementById('universe-labels');
    if (labelsEl) labelsEl.innerHTML = '';
    _uLabelEls    = [];
    _uSecLabelEls = [];

    // ── Gate connections (neon lines) ────────────────────────────────────────
    // Pre-compute each sector's sub-hex SVG center using the same offset
    // assignment as the cluster loop below, so line endpoints match exactly.
    const sectorPos = {};
    for (const [_m, [_q, _r]] of Object.entries(CLUSTER_POS)) {
      const { x: _cx, y: _cy } = hexCenter(_q, _r);
      const _secs = (clusterInfo[_m] || {}).sectors || [];
      if (!_secs.length) continue;
      const _lay = SECTOR_LAYOUTS[Math.min(_secs.length, SECTOR_LAYOUTS.length) - 1];
      _secs.forEach((sec, i) => {
        const [ox, oy] = _lay.offs[i] || [0, 0];
        sectorPos[sec.sector_macro] = {
          clusterMacro: _m,
          cx: _cx, cy: _cy,
          sx: _cx + ox * HEX_BODY,
          sy: _cy + oy * HEX_BODY,
          // Gate positions are ±300 km in sector space; scale them to this
          // cluster's sub-hex radius (which varies with sector count).
          gateScale: (_lay.r * HEX_BODY) / 300,
          color: FACTION_COLOURS[sec.owner_id] || '#6e7681',
          discovered: !!sec.is_discovered,
        };
      });
    }

    // <defs> lives on <svg> (not the viewport <g>) so it survives vp clears.
    const svgEl = document.getElementById('universe-svg');
    const oldDefs = svgEl.querySelector('defs');
    if (oldDefs) oldDefs.remove();
    const defs = document.createElementNS(SVG_NS, 'defs');
    svgEl.insertBefore(defs, svgEl.firstChild);

    // Blur filter — the wide glow stroke uses this; the core line does not.
    const _nf = document.createElementNS(SVG_NS, 'filter');
    _nf.id = 'u-neon';
    // Tight margins — just enough for the 2.5-unit blur to expand without clipping.
    // Applied to a group (not individual lines), so the bounding box is always 2D.
    _nf.setAttribute('x', '-0.5%'); _nf.setAttribute('y', '-0.5%');
    _nf.setAttribute('width', '101%'); _nf.setAttribute('height', '101%');
    const _gb = document.createElementNS(SVG_NS, 'feGaussianBlur');
    _gb.setAttribute('stdDeviation', '2.5');
    _nf.appendChild(_gb); defs.appendChild(_nf);

    // cgCluster is appended before the hex loop (behind hexes).
    // cgSector is appended after the hex loop (in front of hexes).
    // Each is split into a glow sub-group (filter applied once to the whole group,
    // so the bbox is never degenerate for axis-aligned lines) and a core sub-group.
    const cgCluster = el('g', { id: 'u-conns-cluster' });
    const cgClGlow  = el('g', { filter: 'url(#u-neon)' });
    const cgClCore  = el('g', {});
    cgCluster.appendChild(cgClGlow);
    cgCluster.appendChild(cgClCore);
    const cgSector  = el('g', { id: 'u-conns-sector', class: 'u-conn-sector' });
    const cgSecGlow = el('g', { filter: 'url(#u-neon)' });
    const cgSecCore = el('g', {});
    cgSector.appendChild(cgSecGlow);
    cgSector.appendChild(cgSecCore);

    // Extract the cluster number from a cluster_macro string (e.g. "cluster_401_macro" → 401).
    function clusterNum(macro) {
      const m = (macro || '').match(/cluster_0*(\d+)_macro/i);
      return m ? parseInt(m[1], 10) : null;
    }

    // Return the SVG position of the gate in sectorMacro that connects to targetClusterMacro.
    // gateScale converts ±300 km sector space to that sector's sub-hex radius
    // (per-sector because sub-hex size now depends on the cluster's sector count).
    // Falls back to the sector sub-hex centre (fallbackX, fallbackY) when not found.
    function gateXY(sectorMacro, targetClusterMacro, fallbackX, fallbackY, gateScale) {
      const tgt   = clusterNum(targetClusterMacro);
      const gates = GATE_POS[(sectorMacro || '').toLowerCase()];
      if (tgt && gates) {
        const g = gates.find(entry => entry[2] === tgt);
        if (g) return { x: fallbackX + g[0] * gateScale,
                        y: fallbackY - g[1] * gateScale }; // negate z → SVG y
      }
      return { x: fallbackX, y: fallbackY };
    }

    (data.galaxy_map?.edges || []).forEach((edge, i) => {
      const a = sectorPos[edge[0]];
      const b = sectorPos[edge[1]];
      if (!a || !b) return;
      // Fog-of-war: never draw a jump-line that touches an undiscovered sector
      // (applies to both the cluster-level and sector-level strands below).
      if (!a.discovered || !b.discovered) return;

      const id = `ug${i}`;

      // Cross-cluster lines
      if (a.clusterMacro !== b.clusterMacro) {
        const ca = clusterColour(a.clusterMacro);
        const cb = clusterColour(b.clusterMacro);
        const gc = el('linearGradient', {
          id: id + 'c', gradientUnits: 'userSpaceOnUse',
          x1: a.cx, y1: a.cy, x2: b.cx, y2: b.cy,
        });
        gc.appendChild(el('stop', { offset: '0%',   'stop-color': ca }));
        gc.appendChild(el('stop', { offset: '100%', 'stop-color': cb }));
        defs.appendChild(gc);
        cgClGlow.appendChild(el('line', {
          x1: a.cx, y1: a.cy, x2: b.cx, y2: b.cy,
          stroke: `url(#${id}c)`, 'stroke-width': '6', opacity: '0.28',
        }));
        cgClCore.appendChild(el('line', {
          x1: a.cx, y1: a.cy, x2: b.cx, y2: b.cy,
          stroke: `url(#${id}c)`, 'stroke-width': '1.2', opacity: '0.80',
        }));
      }

      // Sector-level lines (with gate-position precision, fallback to sub-hex centre)
      const ptA = gateXY(edge[0], b.clusterMacro, a.sx, a.sy, a.gateScale);
      const ptB = gateXY(edge[1], a.clusterMacro, b.sx, b.sy, b.gateScale);
      const gs = el('linearGradient', {
        id: id + 's', gradientUnits: 'userSpaceOnUse',
        x1: ptA.x, y1: ptA.y, x2: ptB.x, y2: ptB.y,
      });
      gs.appendChild(el('stop', { offset: '0%',   'stop-color': a.color }));
      gs.appendChild(el('stop', { offset: '100%', 'stop-color': b.color }));
      defs.appendChild(gs);
      cgSecGlow.appendChild(el('line', {
        x1: ptA.x, y1: ptA.y, x2: ptB.x, y2: ptB.y,
        stroke: `url(#${id}s)`, 'stroke-width': '3.5', opacity: '0.35',
      }));
      cgSecCore.appendChild(el('line', {
        x1: ptA.x, y1: ptA.y, x2: ptB.x, y2: ptB.y,
        stroke: `url(#${id}s)`, 'stroke-width': '0.7', opacity: '0.85',
      }));
    });

    vp.appendChild(cgCluster);

    for (const [macro, [q, r]] of Object.entries(CLUSTER_POS)) {
      const { x: cx, y: cy } = hexCenter(q, r);
      const colour   = clusterColour(macro);
      const sectors  = (clusterInfo[macro] || {}).sectors || [];

      const g = el('g', { class: 'u-cluster', 'data-macro': macro });

      // Cluster hex body (inset by 1.5 SVG units for a visible gap between adjacent hexes)
      g.appendChild(el('polygon', {
        points:        hexPoints(cx, cy, BASE_HEX - 1.5),
        fill:          hexToRgba(colour, 0.06),
        stroke:        hexToRgba(colour, 0.50),
        'stroke-width': '1',
      }));

      // Cluster name label — crisp HTML in the flat overlay, repositioned by
      // _uCommitTransform; wx/wy are the hex centre in map world units.
      if (labelsEl) {
        const lbl = document.createElement('span');
        lbl.className = 'u-hex-label';
        lbl.style.color = colour;
        lbl.textContent = clusterDisplayName(macro);
        labelsEl.appendChild(lbl);
        _uLabelEls.push({ el: lbl, wx: cx, wy: cy });
      }

      // Sector sub-hexes (visible at zoom ≥ 1.60).
      // Must use the same layout/position formulas as the sectorPos loop above
      // so gate connection line endpoints match the drawn hexes exactly.
      // Sub-hexes only render for clusters with at least one discovered sector;
      // an entirely-undiscovered cluster shows nothing when zoomed in.
      if (sectors.length > 0 && (clusterInfo[macro] || {}).anyDiscovered) {
        const layout = SECTOR_LAYOUTS[Math.min(sectors.length, SECTOR_LAYOUTS.length) - 1];
        const subR   = layout.r * HEX_BODY;
        const sg     = el('g', { class: 'u-sector-hex' });

        sectors.forEach((sec, i) => {
          const [ox, oy] = layout.offs[i] || [0, 0];
          const sx = cx + ox * HEX_BODY;
          const sy = cy + oy * HEX_BODY;
          const discovered = !!sec.is_discovered;
          const sc = discovered ? (FACTION_COLOURS[sec.owner_id] || '#6e7681')
                                : UNDISCOVERED_COLOUR;

          sg.appendChild(el('polygon', {
            points:         hexPoints(sx, sy, subR - 0.5),
            fill:           hexToRgba(sc, 0.20),
            stroke:         hexToRgba(sc, 0.75),
            'stroke-width': '0.8',
            'data-sector':  sec.sector_macro,
          }));

          // Sector name label — crisp HTML in the flat overlay, like the
          // cluster labels above.
          if (labelsEl) {
            const sl = document.createElement('span');
            sl.className = 'u-sector-label';
            sl.style.color = sc;
            sl.textContent = discovered ? (sec.sector_name || sec.sector_macro) : 'Undiscovered';
            labelsEl.appendChild(sl);
            _uSecLabelEls.push({ el: sl, wx: sx, wy: sy });
          }
        });

        g.appendChild(sg);
      }

      vp.appendChild(g);
    }

    vp.appendChild(cgSector); // in front of hex polygons

    // ── Hover panel data (rebuilt every render in case data changes) ──────────
    _sectorInfoMap = {};
    for (const s of (data.sectors || [])) _sectorInfoMap[s.sector_macro] = s;

    _npcBySector = data.npc_stations_by_sector || {};

    // The player's own stations grouped by sector (data.stations is player-only).
    // Powers the per-sector station count + "Your Stations" list in the Sectors tab.
    _playerStaBySector = {};
    for (const st of (data.stations || [])) {
      if (!st.sector_macro) continue;
      (_playerStaBySector[st.sector_macro] || (_playerStaBySector[st.sector_macro] = [])).push(st);
    }

    // The player's own ships grouped by sector (data.ships is the player fleet).
    // Powers the collapsible "Your Ships" list in the Sectors tab.
    _playerShipsBySector = {};
    for (const sp of (data.ships || [])) {
      if (!sp.sector_macro) continue;
      (_playerShipsBySector[sp.sector_macro] || (_playerShipsBySector[sp.sector_macro] = [])).push(sp);
    }

    // Player standing per faction, so the sector pane can show the owner's tier
    // (using the same tierBadge as the Diplomacy tab).
    _repByFaction = {};
    for (const r of (data.reputation || [])) _repByFaction[r.faction_id] = r;

    // Jump distance from your nearest owned/occupied territory to every sector,
    // for the Core/Frontier/Remote tags. 0 = a sector you're established in.
    _distFromEmpire = data.galaxy_map?.distances_from_player || {};

    // Sector adjacency for the Sectors-tab detail pane: each gate/highway edge
    // is undirected, so record it both ways. cost 0 = intra-cluster highway.
    _sectorAdj = {};
    for (const [a, b, cost] of (data.galaxy_map?.edges || [])) {
      (_sectorAdj[a] || (_sectorAdj[a] = [])).push({ macro: b, cost });
      (_sectorAdj[b] || (_sectorAdj[b] = [])).push({ macro: a, cost });
    }

    // Dijkstra from each player station sector to find the nearest named station
    // for every sector on the map. O(stations × sectors²) but the galaxy is small.
    _nearestStation = {};
    const _stations = data.stations || [];
    if (_stations.length) {
      const _g = new Map();
      for (const [a, b, cost] of (data.galaxy_map?.edges || [])) {
        if (!_g.has(a)) _g.set(a, []);
        if (!_g.has(b)) _g.set(b, []);
        _g.get(a).push([b, cost]);
        _g.get(b).push([a, cost]);
      }
      for (const st of _stations) {
        if (!st.sector_macro) continue;
        const dist = new Map([[st.sector_macro, 0]]);
        const pq   = [[0, st.sector_macro]];
        while (pq.length) {
          pq.sort((x, y) => x[0] - y[0]);
          const [d, u] = pq.shift();
          if (d > (dist.get(u) ?? Infinity)) continue;
          for (const [v, w] of (_g.get(u) || [])) {
            const nd = d + w;
            if (nd < (dist.get(v) ?? Infinity)) { dist.set(v, nd); pq.push([nd, v]); }
          }
        }
        for (const [sec, d] of dist) {
          const cur = _nearestStation[sec];
          if (!cur || d < cur.jumps) _nearestStation[sec] = { name: st.name, jumps: d };
        }
      }
    }

    // ── Pan / zoom event handlers (attached once) ─────────────────────────────
    if (!_universeBuilt) {
      const wrap = document.getElementById('universe-map-wrap');

      // Apply the tilt from the JS constants — single source of truth, so the
      // projection helpers can never disagree with what the GPU renders.
      wrap.style.perspective = U_TILT_DEG ? `${U_TILT_PERSP}px` : 'none';
      const tiltEl = document.getElementById('universe-tilt');
      if (tiltEl) tiltEl.style.transform = U_TILT_DEG ? `rotateX(${U_TILT_DEG}deg)` : 'none';

      // Cursor → flat map space: undo the tilt projection. Gives exact
      // zoom-to-cursor and drag-follows-grab on the tilted plane.
      function cursorToMap(e) {
        const rect = wrap.getBoundingClientRect();
        return _uTiltUnproject(e.clientX - rect.left, e.clientY - rect.top,
                               wrap.clientWidth, wrap.clientHeight);
      }

      // Scroll-to-zoom centred on cursor position
      wrap.addEventListener('wheel', function(e) {
        e.preventDefault();
        const factor   = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const m        = cursorToMap(e);
        const t        = _universeTransform;
        const newScale = Math.max(0.10, Math.min(12, t.scale * factor));
        _universeTransform = {
          scale: newScale,
          x: m.x - (m.x - t.x) * (newScale / t.scale),
          y: m.y - (m.y - t.y) * (newScale / t.scale),
        };
        _uApplyTransform(_universeTransform);
      }, { passive: false });

      // Drag-to-pan — anchored in map space so the grabbed point stays glued
      // to the cursor even though the plane is tilted.
      let _dragging = false, _dragOrigin = null, _downScreen = null, _moved = false;
      wrap.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        const m     = cursorToMap(e);
        _dragging   = true;
        _downScreen = { x: e.clientX, y: e.clientY };
        _moved      = false;
        _dragOrigin = { x: m.x - _universeTransform.x, y: m.y - _universeTransform.y };
        wrap.classList.add('panning');
      });
      window.addEventListener('mousemove', function(e) {
        if (!_dragging) return;
        // Past a few pixels this is a pan, not a click — used to suppress the
        // click-to-open-sector that would otherwise fire on mouseup.
        if (_downScreen && Math.hypot(e.clientX - _downScreen.x, e.clientY - _downScreen.y) > 4) _moved = true;
        const m = cursorToMap(e);
        _universeTransform.x = m.x - _dragOrigin.x;
        _universeTransform.y = m.y - _dragOrigin.y;
        _uApplyTransform(_universeTransform);
      });
      window.addEventListener('mouseup', function() {
        if (!_dragging) return;
        _dragging = false;
        document.getElementById('universe-map-wrap')?.classList.remove('panning');
      });

      // Sector hover panel — delegated to the map so we only attach one listener.
      wrap.addEventListener('mousemove', function(e) {
        if (_dragging) { _hideUHoverPanel(); return; }
        const hex = e.target.closest('[data-sector]');
        if (hex) {
          _showUHoverPanel(hex.dataset.sector, e.clientX + 14, e.clientY + 14);
        } else {
          _hideUHoverPanel();
        }
      });
      wrap.addEventListener('mouseleave', _hideUHoverPanel);

      // Click a sector sub-hex (visible when zoomed in) to open its card on the
      // Sectors tab. Skipped after a pan so dragging the map never navigates.
      wrap.addEventListener('click', function(e) {
        if (_moved) return;
        const hex = e.target.closest('[data-sector]');
        if (hex) goToSector(hex.dataset.sector);
      });

      _universeBuilt = true;
    }

    _uApplyTransform(_universeTransform);
  }

  function _showUHoverPanel(sectorMacro, clientX, clientY) {
    const panel = document.getElementById('u-hover-panel');
    if (!panel) return;

    const sec  = _sectorInfoMap[sectorMacro];
    const near = _nearestStation[sectorMacro];
    const facs = _npcBySector[sectorMacro] || [];

    const secName   = sec?.sector_name  || sectorMacro;
    // Strip the [ABR] bracket prefix that FACTION_NAMES includes (e.g. "[TEL] Teladi")
    const ownRaw    = sec?.owner_name   || '';
    const ownName   = ownRaw.replace(/^\[\w+\]\s*/, '') || 'Unclaimed';
    const ownColor  = FACTION_COLOURS[sec?.owner_id] || 'var(--text-secondary)';

    let html = `<div class="uhp-name">${secName}</div>
<div class="uhp-owner" style="color:${ownColor}">${ownName}</div>`;

    if (near) {
      const jLabel = near.jumps === 0 ? 'here' : `${near.jumps} jump${near.jumps !== 1 ? 's' : ''}`;
      html += `<div class="uhp-sep"></div>
<div class="uhp-nearest"><span class="uhp-stname">${near.name}</span><span class="uhp-jumps">${jLabel}</span></div>`;
    }

    if (facs.length) {
      const rows = facs.map(f => {
        const m     = f.owner_name.match(/^\[(\w+)\]/);
        const short = m ? m[1] : f.owner_name.slice(0, 3).toUpperCase();
        const color = FACTION_COLOURS[f.owner_id] || '#6e7681';
        return `<div class="uhp-faction-row">
  <span class="uhp-fdot" style="background:${color}"></span>
  <span class="uhp-fcode">${short}</span>
  <span class="uhp-fcount">${f.count}</span>
</div>`;
      }).join('');
      html += `<div class="uhp-sep"></div><div>${rows}</div>`;
    }

    panel.innerHTML = html;
    // Add visible before reading dimensions — offsetWidth/Height are 0 while
    // display:none, so we need layout to happen first. Browsers batch paint with
    // JS execution, so the position is set in the same frame as the class add.
    panel.classList.add('visible');
    const pw = panel.offsetWidth;
    const ph = panel.offsetHeight;
    panel.style.left = Math.min(clientX, window.innerWidth  - pw - 8) + 'px';
    panel.style.top  = Math.min(clientY, window.innerHeight - ph - 8) + 'px';
  }

  function _hideUHoverPanel() {
    document.getElementById('u-hover-panel')?.classList.remove('visible');
  }

