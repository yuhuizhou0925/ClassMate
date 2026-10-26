"""Offline demo: scripted lecture + canned answers, no API keys or microphone needed."""
from __future__ import annotations

import asyncio

from .asr import Transcript

LECTURE = [
    "Okay everyone, let's get started with feature matching.",
    "Last week we computed SIFT descriptors for each keypoint.",
    "Why do we use the ratio test when matching descriptors?",
    "Think about what happens with repeated textures like windows on a building.",
    "Now, RANSAC fits a homography from noisy matches.",
    "How many point correspondences do we need to estimate a homography?",
]
ANSWERS = {
    "ratio": "比值检验（ratio test）用来剔除模糊的匹配：只有最近邻距离明显小于次近邻距离时才保留这个匹配。\n"
             "- 重复纹理会产生好几个几乎一样的候选\n- 阈值取 0.7–0.8 左右能去掉大部分错误匹配\n"
             "- 外点（outliers）少了，RANSAC 也更快",
    "homography": "需要 4 对点对应（任意三点不共线），因为单应性（homography）有 8 个自由度，每对点提供 2 个方程。\n"
                  "- 点更多时用最小二乘提高鲁棒性\n- RANSAC 每次随机取 4 对点",
}


class DemoSource:
    finished = False

    async def start(self, queue):
        async def pump():
            for _ in range(10 ** 6):
                await queue.put(b"\0" * 1600)
                await asyncio.sleep(0.05)
        self._task = asyncio.create_task(pump())

    async def stop(self):
        self._task.cancel()


class DemoASR:
    async def run(self, queue, emit):
        for sentence in LECTURE:
            words = sentence.split()
            for i in range(1, len(words) + 1, 2):
                await asyncio.sleep(0.25)
                await emit(Transcript(" ".join(words[:i]), final=False))
            await asyncio.sleep(0.3)
            await emit(Transcript(sentence, final=True, end_of_turn=True))
            await asyncio.sleep(1.2)
        while True:
            await asyncio.sleep(3600)


async def demo_grab(folder, region=False, max_side=1568):
    """Stand-in for a screenshot: renders a slide with a question on it."""
    from pathlib import Path
    from PIL import Image, ImageDraw
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"demo_{len(list(folder.glob('demo_*.jpg'))) + 1}.jpg"
    im = Image.new("RGB", (960, 540), (250, 250, 247))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 960, 70], fill=(47, 111, 94))
    d.text((30, 25), "COMP90086  Week 10  Quiz", fill="white")
    d.text((40, 140), "Q3. A camera rotates about its optical centre.", fill=(30, 30, 30))
    d.text((40, 180), "Which model relates the two images: affine, homography or fundamental matrix?",
           fill=(30, 30, 30))
    d.text((40, 240), "(a) affine   (b) homography   (c) fundamental matrix", fill=(90, 90, 90))
    im.save(path, "JPEG", quality=85)
    return path


SHOT_ANSWER = (
    "**题目：** Q3. 相机绕光心旋转。哪种模型描述两幅图像之间的关系：(a) 仿射 (b) 单应性 (c) 基础矩阵？\n\n"
    "**解答：**\n"
    "#### 正确答案：(b) 单应性（homography）\n"
    "1. 纯旋转 R、内参 K 时，图 1 的像素 x 映射到图 2 为 x' = K R K^-1 x。\n"
    "2. 这是一个只差一个尺度的 3x3 可逆矩阵，也就是单应性 H = K R K^-1。\n"
    "3. 没有平移，深度被消掉，所以所有场景点都服从同一个 H。\n\n"
    "为什么不是其他两个：\n"
    "- **(a) 仿射（affine）** 保持平行线平行；相机旋转会带来透视变化，仿射限制太强。\n"
    "- **(c) 基础矩阵（fundamental matrix）** 只把点约束到极线上，而且需要平移；纯旋转时极几何退化。\n\n"
    "```python\nH = K @ R @ np.linalg.inv(K)   # 把图 1 变换到图 2\n```")


ENGINEER_ANSWER = (
    "### 核心结论\n用比值检验（ratio test）过滤 SIFT 匹配：只保留最近邻明显比次近邻更近的匹配。\n\n"
    "### 工程方案\n1. 提取特征：`cv2.SIFT_create(nfeatures=4000)`，灰度图输入\n"
    "2. 近邻搜索：FLANN KD 树，`trees=5`、`checks=50`，每个描述子取 k=2 个近邻\n"
    "3. 比值检验：保留 $d_1 < 0.75\\, d_2$ 的匹配\n4. 去重：同一目标点只保留距离最小的一条\n"
    "5. 几何校验：`cv2.findHomography(..., cv2.RANSAC, 3.0)`，只留内点\n\n"
    "```python\nimport cv2\n\ndef match(img1, img2, ratio=0.75):\n    sift = cv2.SIFT_create(nfeatures=4000)        # 1\n"
    "    k1, d1 = sift.detectAndCompute(img1, None)\n    k2, d2 = sift.detectAndCompute(img2, None)\n"
    "    flann = cv2.FlannBasedMatcher({'algorithm': 1, 'trees': 5}, {'checks': 50})   # 2\n"
    "    pairs = flann.knnMatch(d1, d2, k=2)\n"
    "    return [m for m, n in pairs if m.distance < ratio * n.distance]   # 3\n```\n\n"
    "### 方案解释\n1. SIFT 对尺度和旋转不变，4000 个点在速度和覆盖之间折中。\n"
    "2. 精确最近邻是 $O(NMD)$，KD 树近似搜索快一个数量级。\n"
    "3. 正确匹配满足 $$\\frac{d_1}{d_2} \\ll 1,$$ 重复纹理会让比值接近 1，0.75 是 Lowe 论文推荐值。\n"
    "4. 多对一匹配会让单应性估计偏向重复区域。\n5. RANSAC 去掉比值检验漏掉的外点。\n\n"
    "### 延伸\n- 为什么不用固定距离阈值？描述子距离尺度随图像变化，比值是相对量。")


class DemoAnswerer:
    async def stream(self, question, transcript, notes, deep=False, history=(), images=(), engineer=False,
                     previous=""):
        if engineer:
            text = ENGINEER_ANSWER
        elif images:
            text = SHOT_ANSWER
        else:
            text = ANSWERS["homography" if "homography" in question.lower() else "ratio"]
        await asyncio.sleep(0.35)
        for token in text.split(" "):
            await asyncio.sleep(0.01)
            yield token + " "

    async def warmup(self):
        return None
