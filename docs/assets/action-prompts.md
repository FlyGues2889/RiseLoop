# 动作示意图生成清单

给 9 个动作各出一张示意图，用来替换「看不到摄像头 / 不想开摄像头」时的空白区域。
字段与 `data/actions/actions.json` 一致，文件名直接用动作 id。

## 一、统一风格（每条提示词前面都拼上这段）

**中文风格句**

> 扁平矢量插画，圆润简洁的几何造型，浅薄荷色渐变背景，人物穿低饱和绿色与暖灰色运动服，
> 单人单动作、全身或大腿以上构图，三分之四侧视角，柔和环境阴影，画面干净留白，
> 不出现任何文字、logo、水印，横构图 4:3。

**English style block**

> flat vector illustration, rounded simple geometry, pale mint gradient background,
> person in muted green and warm grey activewear, single person single pose,
> three-quarter view, soft ambient shadow, clean uncluttered composition,
> no text, no logo, no watermark, 4:3 landscape.

**负向提示词（Negative）**

> photo, photorealistic, real skin texture, text, letters, caption, watermark,
> logo, brand mark, busy background, furniture clutter, multiple people,
> multiple panels, collage, deformed hands, extra fingers, extra limbs, cropped head

## 二、通用要求

- 一张图只讲一个动作，不做分格连环画（步骤文字由界面显示）。
- 人物占画面约 70%，头顶留空 8%，便于裁切。
- 背景不要出现人脸、屏幕、办公室杂物，避免和摄像头画面抢注意力。
- 必须体现「坐姿」还是「站立／跪姿」——这是用户最需要一眼看懂的信息。
- 输出 1024×768（或 1024×1024 后裁切），转 jpg 或 webp，放到
  `apps/desktop-tauri/src/assets/actions/<action-id>.jpg`。
- 不用把图叠在摄像头画面上：放在摄像头卡片旁或下方，点开放大；摄像头没开时用它占位。

## 三、逐动作清单

### 1. s0-neck-release · 坐姿颈部缓慢放松

- 状态 / 场景：S0 · 坐姿 · 工位可做 · 2 分钟
- 要点
  1. 坐直、双脚踩地、肩膀下沉，不要塌腰。
  2. 低头时下巴找胸口，停 5 秒，动作要慢。
  3. 侧屈是「耳朵靠肩」，不耸肩、不转体；出现眩晕或放射痛立即停。
- 画面：坐在办公椅上，右手轻扶左侧头部，头向右肩侧倾，肩膀保持水平。
- 提示词（中）

> 【风格句】一个人坐在办公椅上做颈部侧向拉伸：躯干挺直、双脚踩地，右手扶住左侧头顶，头缓慢倒向右侧，左肩明显下沉放松，表情平静。画面只出现椅面上半身，背景浅薄荷渐变。

- 提示词（EN）

> 【style block】 a person seated upright on an office chair doing a gentle neck side stretch:
> back straight, feet flat on the floor, right hand lightly resting on the left side of the head,
> head tilted toward the right shoulder, left shoulder relaxed and lowered, calm expression,
> framed from the waist up, empty pale background.

### 2. s0-shoulder-roll · 肩胛绕环与胸椎伸展

- 状态 / 场景：S0 · 坐姿 · 工位可做 · 2 分钟
- 要点
  1. 双手搭同侧肩，肘部朝前，别夹脖子。
  2. 肘部画大圆，慢到能感觉到肩胛在滑动。
  3. 抱头后展时只展胸椎，不要仰脖子；幅度以不痛为限。
- 画面：坐姿，双手分别搭在两侧肩上，肘部抬起画圆，胸腔打开。
- 提示词（中）

> 【风格句】一个人坐着把双手搭在同侧肩膀上，手肘抬高、向前画圈，胸腔轻轻打开，肩胛向后收；上半身构图，椅背可见，背景浅薄荷渐变。

- 提示词（EN）

> 【style block】 a seated person with both hands placed on the same-side shoulders,
> elbows lifted forward mid-circle, chest slightly open, shoulder blades drawing back,
> waist-up framing with part of the chair visible, empty pale background.

### 3. s1-seated-knee · 坐姿伸膝与踝泵

- 状态 / 场景：S1 · 坐姿 · 工位可做 · 3 分钟
- 要点
  1. 坐直，膝盖与髋同宽，双脚踩实。
  2. 伸膝时脚尖回勾，大腿前侧收紧，停 5 秒。
  3. 左右交替，别憋气；膝或髋出现锐痛立即停。
- 画面：坐姿，左腿向前伸直、脚尖回勾，右腿屈膝踩地，双手扶椅面。
- 提示词（中）

> 【风格句】一个人坐在椅子上做坐姿伸膝：左腿向前伸直、脚尖朝上回勾，右腿屈膝踩地，躯干直立不后仰，双手轻放腿上；侧面视角，全身入画，背景浅薄荷渐变。

- 提示词（EN）

> 【style block】 a person seated on a chair performing a seated knee extension:
> left leg straightened forward with toes pulled up, right foot flat on the floor,
> torso upright without leaning back, hands resting on the thighs, side view, full body,
> empty pale background.

### 4. s1-stand-break · 起身站立微活动

- 状态 / 场景：S1 · 站立 · 需要离座 · 3 分钟
- 要点
  1. 起身放慢，避免体位性眩晕。
  2. 双脚与髋同宽、膝盖微屈，不要锁死。
  3. 双手十指交叉上举伸展；抬膝时保持躯干直立，别弓背。
- 画面：站立，双手十指交叉举过头顶向上伸展，膝盖微屈。
- 提示词（中）

> 【风格句】一个人从工位站起来做全身伸展：双脚与髋同宽，膝盖微屈，双手十指交叉举过头顶向上延伸，肩部放松，躯干拉长；全身构图，背景只有极淡的地面线，浅薄荷渐变。

- 提示词（EN）

> 【style block】 a person standing beside a desk doing a full-body stretch:
> feet hip-width apart, knees slightly bent, hands clasped above the head reaching upward,
> shoulders relaxed, spine lengthened, full-body framing, minimal floor line,
> empty pale background.

### 5. s1-hip-flexor · 弓步髋前侧拉伸

- 状态 / 场景：S1 · 跪姿弓步 · 需要地面 · 2 分钟
- 要点
  1. 后膝跪在垫上，前腿屈膝约 90 度。
  2. 骨盆轻轻后倾（尾骨向下），才会拉到髋前侧。
  3. 每侧停 20 秒，不塌腰、不往前顶；膝盖不适就加软垫。
- 画面：半跪弓步，后膝着垫，骨盆后倾，上身直立。
- 提示词（中）

> 【风格句】一个人做半跪弓步髋前侧拉伸：后膝跪在软垫上，前腿屈膝约九十度、脚掌踩实，骨盆轻轻后倾，上身直立、双手叉腰；侧面视角，全身入画，浅薄荷渐变背景。

- 提示词（EN）

> 【style block】 a person in a half-kneeling lunge hip-flexor stretch:
> rear knee on a soft mat, front leg bent about ninety degrees with foot flat,
> pelvis gently tucked under, torso upright with hands on hips, side view, full body,
> empty pale background.

### 6. s2-core-activation · 坐姿核心激活

- 状态 / 场景：S2 · 坐姿 · 工位可做 · 2 分钟
- 要点
  1. 坐骨压实椅面，脊柱向上延展，双脚踩地。
  2. 呼气收腹，感觉肋骨下沉，不要塌腰或耸肩。
  3. 骨盆前后倾幅度要小，靠腹部控制而不是用手推。
- 画面：坐姿，一只手放在下腹，脊柱拉长，肩部下沉。
- 提示词（中）

> 【风格句】一个人端坐在椅子前缘做核心激活：坐骨压实椅面、脊柱向上延展、双脚踩地，一只手轻放在下腹感受收紧，肩膀下沉，表情专注；上半身构图，浅薄荷渐变背景。

- 提示词（EN）

> 【style block】 a person sitting tall on the front edge of a chair doing a core activation drill:
> sit bones grounded, spine lengthened upward, feet flat, one hand lightly on the lower abdomen,
> shoulders relaxed down, focused expression, waist-up framing, empty pale background.

### 7. s2-band-row · 弹力带划船

- 状态 / 场景：S2 · 坐姿 · 工位可做 · 3 分钟
- 要点
  1. 弹力带固定在胸前高度，双手各握一端。
  2. 先收肩胛，再让肘部后拉，不耸肩。
  3. 回放要慢（约 2 秒），别让带子弹回；没有弹力带可用毛巾做等长收缩。
- 画面：坐姿，双手拉弹力带向后，肘部贴近身体。
- 提示词（中）

> 【风格句】一个人坐着用弹力带做划船：弹力带固定在胸前高度，双手各握一端，肩胛向后收紧、肘部贴近身体向后拉，躯干保持直立不后仰；上半身构图，弹力带线条清晰，浅薄荷渐变背景。

- 提示词（EN）

> 【style block】 a seated person doing a resistance-band row:
> band anchored at chest height, one end in each hand, shoulder blades squeezed back,
> elbows pulling back close to the ribs, torso upright without leaning back,
> waist-up framing, clear band line, empty pale background.

### 8. s3-posture-reset · 靠墙体态重置

- 状态 / 场景：S3 · 站立靠墙 · 需要空墙 · 2 分钟
- 要点
  1. 后脑、肩胛、骨盆依次贴墙，不必强求全部接触。
  2. 收下巴、后颈延长，别把头顶往后顶。
  3. 保持贴墙做 5 次深呼吸，离开墙后回到坐姿感受背部位置。
- 画面：背靠墙站立，后脑与肩胛贴墙，下巴微收。
- 提示词（中）

> 【风格句】一个人背靠白墙站立做体态重置：后脑、肩胛、骨盆依次贴墙，下巴微收、后颈延长，双脚离墙约一脚距离，双臂自然下垂；侧面视角，全身入画，墙面为极浅灰，浅薄荷渐变背景。

- 提示词（EN）

> 【style block】 a person standing with the back against a plain wall for a posture reset:
> back of the head, shoulder blades and pelvis touching the wall, chin slightly tucked,
> neck lengthened, feet about one foot away from the wall, arms relaxed at the sides,
> side view, full body, very light grey wall, empty pale background.

### 9. s3-breathe · 坐姿呼吸放松

- 状态 / 场景：S3 · 坐姿 · 工位可做 · 3 分钟
- 要点
  1. 一手放胸口、一手放腹部，只有腹部明显起伏。
  2. 吸气 4 秒、呼气 6 秒、停 2 秒，别用力吸。
  3. 觉得憋气或头晕就改回自然呼吸。
- 画面：坐姿，双手分别放在胸口与腹部，闭眼放松。
- 提示词（中）

> 【风格句】一个人坐着做腹式呼吸放松：躯干挺直、双脚踩地，一手放胸口、一手放腹部，闭眼、肩部放松，胸口几乎不动而腹部轻微起伏；上半身构图，浅薄荷渐变背景。

- 提示词（EN）

> 【style block】 a seated person practising slow diaphragmatic breathing:
> upright posture, feet flat, one hand on the chest and one on the belly, eyes closed,
> shoulders relaxed, chest almost still with the belly gently rising,
> waist-up framing, empty pale background.

## 四、批量出图时的小抄

- 每条提示词 = 风格句 + 本动作主体句 + 负向词，三段拼接。
- 一次只出一个动作，改主体句即可，风格句保持逐字一致，9 张才像一套。
- 出图后检查三件事：手指数对不对、有没有水印、坐/站是否画对（这条最容易画错）。
- 文件名对照：
  `s0-neck-release.jpg`、`s0-shoulder-roll.jpg`、`s1-seated-knee.jpg`、
  `s1-stand-break.jpg`、`s1-hip-flexor.jpg`、`s2-core-activation.jpg`、
  `s2-band-row.jpg`、`s3-posture-reset.jpg`、`s3-breathe.jpg`。
