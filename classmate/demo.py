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
    "### 核心结论\n比值检验（ratio test）只保留“最近邻距离明显小于次近邻距离”的匹配，用一个相对阈值剔除模糊匹配。\n\n"
    "### 原理与推导\n设描述子 d 的最近邻距离为 d1、次近邻为 d2，保留条件为 d1 / d2 < r（常取 0.7–0.8）。"
    "正确匹配的 d1 远小于 d2；重复纹理会让 d1 ≈ d2，比值接近 1。\n\n"
    "### 工程实现\n```python\nimport cv2\n\ndef ratio_match(desc1, desc2, ratio=0.75):\n"
    "    matcher = cv2.BFMatcher(cv2.NORM_L2)\n    pairs = matcher.knnMatch(desc1, desc2, k=2)\n"
    "    return [m for m, n in pairs if m.distance < ratio * n.distance]\n```\n\n"
    "### 复杂度与性能\n暴力匹配 O(N·M·D)；描述子多时改用 FLANN（KD 树）近似最近邻。\n\n"
    "### 边界情况与常见坑\n- 候选少于 2 个时 knnMatch 返回不足两项，需要先过滤\n- 二进制描述子（ORB）要用 NORM_HAMMING\n\n"
    "### 测试与验证\n用已知单应性合成一对图像，统计内点率。\n\n"
    "### 工程取舍与替代方案\n交叉验证（cross-check）更严格但更慢；学习型匹配器（SuperGlue）效果更好但需要 GPU。")


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
