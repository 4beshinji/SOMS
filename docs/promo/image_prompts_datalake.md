# SOMS Data Lake / プライバシー保護フェデレーション 画像生成AIプロンプト集

スライド・記事・ウェブサイト用のビジュアル素材を生成するためのプロンプト集。
DALL-E 3 / Midjourney / Stable Diffusion 向けに最適化。
プライバシー保護型都市データレイク・分散フェデレーションをビジュアルの主軸とする。

---

## 1. ヒーローイメージ: Privacy Shield City (メインビジュアル)

**用途**: LP ヒーロー, プレゼン表紙, SNS OGP画像

**コンセプト**: 都市の俯瞰。各建物が半透明のドーム/シールドで覆われ、データ主権を表現。建物間は微小な光の粒子 (集約データ) だけが流れ、生データはドーム内に留まる。

### DALL-E 3 / ChatGPT

```
An aerial view of a modern city at dusk, rendered in deep teal and blue tones.
Each building is enclosed in a subtle translucent dome or shield, glowing faintly
with a warm amber light from within — representing data sovereignty. The domes
are semi-transparent, allowing the buildings inside to be visible. Between the
buildings, thin luminous threads connect them, but only tiny glowing teal particles
flow along these threads toward a central node in the city center — representing
aggregate statistical data. Inside each dome, warm amber particles swirl densely
around the building (raw data staying local). The central node is a modest
crystalline structure emitting a cool white glow (the city-level aggregator).
The sky is twilight purple-blue, grounded and not dystopian. The overall feel
is trustworthy and protective, not surveillance-like. Futuristic but grounded
aesthetic, blue-teal palette with amber accents, photorealistic, cinematic
lighting, bird's eye perspective, 16:9 aspect ratio.
```

### Midjourney

```
/imagine aerial view modern city at dusk, deep teal blue palette, each building
enclosed in subtle translucent protective dome glowing warm amber from within,
thin luminous threads between buildings carrying only tiny teal particles toward
central node, warm amber particles dense inside each dome representing local data,
central crystalline aggregator node cool white glow, twilight sky, futuristic but
grounded trustworthy aesthetic, photorealistic cinematic lighting bird's eye
--ar 16:9 --v 6.1 --style raw
```

### Stable Diffusion (SDXL)

```
Prompt: aerial view modern city at dusk, deep teal blue palette, each building
enclosed in translucent protective dome glowing warm amber, thin luminous threads
between buildings with tiny teal particles flowing to central node, raw data stays
inside domes, central aggregator cool white glow, twilight sky, futuristic grounded
trustworthy, photorealistic cinematic
Negative: cartoon, anime, low quality, blurry, surveillance cameras, Big Brother,
dystopian, threatening, dark oppressive, CCTV, eye symbols
Steps: 30, CFG: 7, Size: 1920x1080
```

---

## 2. 3-Layer Privacy Architecture (概念断面図)

**用途**: 技術スライド, アーキテクチャ説明, LP アーキテクチャセクション

**コンセプト**: 3つの水平レイヤーの断面図。下層 (暖色/オレンジ) は生データ、中間層 (青) はリージョンハブ、上層 (白) は都市アグリゲーター。データが下から上に変換される過程を表現。

### DALL-E 3 / ChatGPT

```
A conceptual cross-section diagram showing three distinct horizontal layers against
a dark navy background (#0a1628). The composition is wide (16:9) and reads bottom
to top:

BOTTOM LAYER (warm orange/amber, #f59e0b tones): Building silhouettes in a row,
each containing chaotic, dense swirling particles of warm amber light representing
raw sensor data. The particles are messy, organic, high-entropy. Small ESP32
circuit board icons are visible inside buildings. A label reads "Raw Data Layer —
ε-differential privacy applied here". Mathematical noise symbols (bell curves,
+/-δ) float around the buildings.

MIDDLE LAYER (blue, #3b82f6 tones): Several flowing streams of blue light converge
from buildings below into regional hub nodes (medium-sized glowing blue spheres).
The data has transformed from chaotic particles into organized flowing streams.
Arrows show aggregation. A Laplace distribution curve is subtly visible.

TOP LAYER (cool white/silver): A single clean node at the top receives refined
streams. Around it, clean statistical charts float — bar charts, smooth curves,
percentages — all in white and light gray. The data is completely transformed
from chaos to clean statistics. No individual data points visible, only aggregate
patterns.

Clear visual gradient from warm chaos (bottom) to cool order (top). Technical
illustration style with subtle glow effects.
```

### Midjourney

```
/imagine conceptual cross-section three horizontal layers dark navy background,
bottom layer warm amber buildings with chaotic swirling particles raw data ESP32
icons mathematical noise symbols, middle layer blue flowing streams converging into
regional hub spheres Laplace curve, top layer cool white single node clean
statistical charts bar graphs smooth curves, gradient from warm chaos to cool order,
technical illustration subtle glow effects --ar 16:9 --v 6.1
```

### Stable Diffusion (SDXL)

```
Prompt: conceptual cross-section diagram three horizontal layers, dark navy
background, bottom warm amber chaotic particles in buildings raw data, middle blue
flowing streams regional hub nodes, top cool white clean statistical charts,
gradient warm chaos to cool order, technical illustration glow effects
Negative: cartoon, anime, low quality, blurry, surveillance, photographs of people,
faces, realistic buildings
Steps: 30, CFG: 7, Size: 1920x1080
```

---

## 3. ESP32 Privacy Guardian (プロダクトフォト)

**用途**: 技術詳細セクション, エッジデバイス紹介, SNS画像

**コンセプト**: ESP32開発ボードのプロダクトフォト。周囲に差分プライバシーの数学記号が浮遊。ボード上に盾/鍵アイコンのホログラム。

### DALL-E 3 / ChatGPT

```
A product photography style close-up shot of an ESP32 development board with a
BME680 environmental sensor attached, placed on a clean white surface. The board
is sharply in focus with soft studio lighting. Surrounding the board, floating in
mid-air with a holographic quality, are mathematical symbols related to differential
privacy: the Greek letter epsilon, a Laplace distribution bell curve, small
noise particles dispersing outward, the symbol delta, and a subtle "epsilon = 1.0"
notation.

Above the ESP32 board, a small translucent holographic shield icon (like a
protective emblem) with a lock symbol inside hovers, emitting a soft teal glow
(#0d9488). The shield represents privacy protection happening at the edge device
level. Tiny amber data particles flow from the sensor INTO the board, but only
teal anonymized particles emerge from the other side of the shield.

Clean white background, product photography lighting with soft shadows, shallow
depth of field focusing on the board. Technical but accessible aesthetic.
```

### Midjourney

```
/imagine product photography close-up ESP32 dev board with BME680 sensor on white
surface, floating holographic mathematical symbols epsilon Laplace distribution
curve delta noise particles, translucent teal shield icon with lock hovering above
board, amber particles flowing into board teal anonymized particles emerging,
clean white background studio lighting shallow depth of field --ar 16:9 --v 6.1
--style raw
```

### Stable Diffusion (SDXL)

```
Prompt: product photography ESP32 development board BME680 sensor white surface,
floating holographic epsilon Laplace curve mathematical symbols, teal shield lock
icon hovering above, amber particles in teal particles out, studio lighting shallow
depth of field, clean technical
Negative: cartoon, anime, low quality, blurry, messy background, cluttered,
watermark, text overlay
Steps: 30, CFG: 7, Size: 1920x1080
```

---

## 4. Data Clean Room vs. Our Approach (比較ビジュアル)

**用途**: 差別化セクション, 問題提起スライド, LP 比較セクション

**コンセプト**: 左右分割比較。左: 従来型 Data Clean Room (冷たいサーバールーム、データが集約される)。右: 分散型アプローチ (温かい都市、データは建物内に留まる)。

### DALL-E 3 / ChatGPT

```
A split-screen comparison image divided vertically in the center, 16:9 aspect ratio.

LEFT HALF — "Centralized Data Clean Room": A cold, sterile server room rendered
in blue-gray tones. Rows of identical server racks under harsh fluorescent lighting.
Multiple thick data streams (depicted as bright white/blue beams) flow FROM the
outside INTO the room through the walls — data being collected and centralized.
A large lock icon on the server room door, but the data is already inside. The
atmosphere is clinical, impersonal, cold. A faint label: "Data moves to computation".
Small building icons on the outside are shown losing their data (dimming).

RIGHT HALF — "Distributed Privacy-Preserving": A warm cityscape at golden hour,
several buildings each glowing with warm amber light from within (data staying
local). Between buildings, only tiny teal sparkles (aggregate statistics) float
gently outward toward a small, modest central node. The buildings retain their
warm glow — their data stays. People are visible through windows, comfortable
and unmonitored. Green trees, warm atmosphere, human-centric. A faint label:
"Computation moves to data".

A thin vertical dividing line separates the halves. Strong visual contrast between
cold/centralized (left) and warm/distributed (right).
```

### Midjourney

```
/imagine split-screen comparison left cold sterile server room blue-gray harsh
fluorescent thick data beams flowing IN from outside centralized clinical, right
warm cityscape golden hour buildings glowing amber data staying local tiny teal
sparkles between buildings people visible through windows green trees human-centric,
strong contrast cold centralized vs warm distributed --ar 16:9 --v 6.1
```

### Stable Diffusion (SDXL)

```
Prompt: split-screen comparison, left side cold server room blue-gray fluorescent
data beams flowing in centralized, right side warm city golden hour buildings
glowing amber tiny teal sparkles between buildings people in windows, contrast
cold clinical vs warm distributed
Negative: cartoon, anime, low quality, blurry, surveillance, dystopian, scary,
threatening atmosphere
Steps: 30, CFG: 7, Size: 1920x1080
```

---

## 5. Urban Breathing Pattern (データビジュアライゼーションアート)

**用途**: 都市ビジョンセクション, データ可視化, プレゼン

**コンセプト**: 都市マップの俯瞰。24時間の集約CO2/占有率データでエリアが脈動。個人データは一切見えない。朝は住宅街、昼はオフィス街、夜は商業エリアが輝く。

### DALL-E 3 / ChatGPT

```
A data visualization art piece showing a stylized city map viewed from directly
above, on a dark navy background (#0a1628). The city is divided into distinct
districts, each pulsing with color representing aggregate CO2 and occupancy levels
over a 24-hour cycle. The image captures a composite/time-lapse effect:

RESIDENTIAL DISTRICTS (top-left): Glow warm orange (#f59e0b) during morning hours
(6-8 AM marker), fade during midday, glow again in evening. Shown with concentric
pulse rings.

OFFICE DISTRICTS (center): Cool blue (#3b82f6) glow intensifies during business
hours (9 AM - 6 PM), with peak intensity at midday. Sharp-edged district boundaries.

COMMERCIAL DISTRICTS (bottom-right): Teal (#0d9488) glow peaks in evening hours
(5-9 PM), with flowing particle trails suggesting foot traffic.

Between districts, subtle gradient flows show the aggregate movement pattern:
orange to blue (morning commute), blue to teal (evening). NO individual dots, NO
tracking lines, NO person markers — only aggregate color intensity and flow
gradients. A small 24-hour clock dial in the corner shows the time progression.

A text overlay reads: "Aggregate patterns only. Zero individual data points."
Clean, minimal data visualization art style. Beautiful and informative.
```

### Midjourney

```
/imagine data visualization art city map from above dark navy background, districts
pulsing different colors aggregate CO2 occupancy, residential warm orange morning
glow, office blue midday intensity, commercial teal evening glow, gradient flows
between districts showing aggregate movement, no individual markers only aggregate
patterns, 24-hour clock dial, minimal beautiful informative --ar 16:9 --v 6.1
```

### Stable Diffusion (SDXL)

```
Prompt: data visualization art stylized city map from above, dark navy background,
districts pulsing colors aggregate data, residential orange morning, office blue
midday, commercial teal evening, gradient flows between districts, no individual
data points only aggregate, 24-hour cycle, minimal beautiful
Negative: cartoon, anime, low quality, blurry, surveillance, tracking dots,
individual markers, GPS trails, person icons
Steps: 30, CFG: 7, Size: 1920x1080
```

---

## 6. Zero Personal Data (ミニマリストグラフィック)

**用途**: SNS投稿, ポスター, LP アイキャッチ, プレゼン強調スライド

**コンセプト**: ミニマリスト。中央に大きな「0」、建物のシルエットで構成。「個人データ送信量: 0 bytes」のテキスト。タイポグラフィ主体。

### DALL-E 3 / ChatGPT

```
A minimalist typographic poster design on a clean white background. In the center,
a very large numeral "0" dominates the composition. The "0" is constructed entirely
from tiny building and city silhouettes — skyscrapers, office buildings, houses,
apartment blocks — all in deep teal (#0d9488), densely packed to form the shape
of the zero. The buildings are detailed enough to be recognizable but small enough
to read as a unified "0" from a distance.

Below the "0", clean Japanese typography reads:
個人データ送信量: 0 bytes

The text is in dark gray (#374151), using a modern sans-serif font. Below that,
in smaller lighter text (#6b7280):
建物の中でデータは完結する。都市には統計だけが届く。

Generous white space surrounds the composition. No decorative elements, no
gradients, no illustrations beyond the building-silhouette zero. The design
should work as both a poster and a social media graphic. Crisp, modern,
typography-focused graphic design.
```

### Midjourney

```
/imagine minimalist typographic poster white background, large numeral zero made
of tiny teal building silhouettes skyscrapers offices houses, Japanese text below
dark gray modern sans-serif, generous white space,
no decorative elements, crisp modern graphic design --ar 1:1 --v 6.1
```

### Stable Diffusion (SDXL)

```
Prompt: minimalist typographic poster, white background, large zero numeral made
of tiny teal building silhouettes, clean Japanese typography below, generous white
space, modern graphic design, crisp sharp
Negative: cartoon, anime, low quality, blurry, colorful, busy, cluttered,
gradients, photographs, realistic
Steps: 30, CFG: 7, Size: 1080x1080
```

---

## スタイルガイドライン (共通)

### カラーパレット

プロンプトに含める色指定:

| 用途 | 色 | Hex |
|---|---|---|
| プライバシー / セキュリティ | ディープティール | `#0d9488` |
| 生データ / ローカル | ウォームアンバー | `#f59e0b` |
| 集約 / フェデレーション | クールブルー | `#3b82f6` |
| 都市レベル / 統計 | ホワイト / ライトグレー | `#f9fafb` |
| 背景 (ダーク) | ディープネイビー | `#0a1628` |
| 成功 / 安全 | グリーン | `#10b981` |
| 警告 | アンバー | `#f59e0b` |
| エラー / 危険 | レッド | `#ef4444` |

### トーン & ムード

- **信頼**: 技術的だがアクセスしやすい、誠実なビジュアル
- **保護**: シールド、ドーム、包み込む光で「守る」イメージ
- **非ディストピア**: 監視社会を連想させない。Big Brother的な表現を避ける
- **温かみ**: データは冷たいものではなく、都市の生活を支える温かい存在
- **分散**: 中央集権的な巨大サーバーではなく、各建物が自律する美しさ
- **数学的美しさ**: 差分プライバシーの数式を装飾的に使う (ε, Laplace, ノイズ)

### 解像度

| 用途 | 推奨サイズ |
|---|---|
| スライド / プレゼン背景 | 1920 x 1080 (16:9) |
| SNS (正方形) | 1080 x 1080 (1:1) |
| 記事アイキャッチ (OGP) | 1200 x 630 |
| ウェブサイトヒーロー | 1920 x 1080 |
| ポスター | 2480 x 3508 (A4, 300dpi) |

### ネガティブプロンプト (共通)

Stable Diffusion 向け:
```
cartoon, anime, low quality, blurry, distorted faces, text, watermark,
signature, oversaturated, surveillance cameras, CCTV, Big Brother,
eye of providence, dystopian, oppressive atmosphere, dark threatening,
cloud computing symbols, AWS/Azure/GCP logos, centralized data center,
tracking dots, GPS trails, individual person markers
```
