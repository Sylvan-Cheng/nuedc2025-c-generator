from __future__ import annotations

import os
import random
import shutil

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageEnhance

from .config import AugmentConfig, FontConfig, FontSelector, YoloExportConfig


def _get_split(yolo_cfg: YoloExportConfig) -> str:
    """随机选择 train/val/test 分割"""
    r = random.random()
    if r < yolo_cfg.train_ratio:
        return "train"
    elif r < yolo_cfg.train_ratio + yolo_cfg.val_ratio:
        return "val"
    return "test"


def _apply_augmentation(
    img: Image.Image,
    augment_cfg: AugmentConfig,
) -> Image.Image:
    """应用数据增强（针对小图片优化）"""
    if not augment_cfg.enable:
        return img

    if random.random() < 0.5:
        angle = random.uniform(-augment_cfg.rotation_range, augment_cfg.rotation_range)
        img = img.rotate(angle, expand=False, fillcolor=(255, 255, 255))

    if random.random() < 0.5:
        factor = random.uniform(*augment_cfg.brightness_range)
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(factor)

    if random.random() < 0.5:
        factor = random.uniform(*augment_cfg.contrast_range)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(factor)

    if augment_cfg.noise_std > 0 and random.random() < 0.3:
        img_array = np.array(img).astype(np.float32)
        noise = np.random.normal(0, augment_cfg.noise_std * 255, img_array.shape)
        img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(img_array)

    return img


def _generate_digit_image(
    digit: int,
    image_size: int,
    digit_size_ratio: float,
    square_ratio: float = 0.8,
    cv_noise_level: int = 5,
    font_cfg: FontConfig | None = None,
    lighting_variation: bool = True,
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    """生成模拟CV裁切后的图像（带误差）

    Args:
        digit: 数字 0-9
        image_size: 图片尺寸
        digit_size_ratio: 数字占正方形的比例 (0-1)
        square_ratio: 正方形占大图的比例 (0-1)
        cv_noise_level: CV裁切误差（像素）
        font_cfg: 字体配置
        lighting_variation: 是否模拟光照变化

    Returns:
        图片和边界框 (cx, cy, w, h) 归一化坐标
    """
    # 1. 创建大尺寸白色背景（包含边距）
    margin = random.randint(5, 20)  # 随机边距
    large_size = image_size + margin * 2
    img = Image.new("RGB", (large_size, large_size), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 2. 计算正方形区域（带随机偏移，模拟CV检测误差）
    square_size = int(large_size * square_ratio)
    square_x = (large_size - square_size) // 2 + random.randint(-cv_noise_level, cv_noise_level)
    square_y = (large_size - square_size) // 2 + random.randint(-cv_noise_level, cv_noise_level)

    # 确保正方形在图像内
    square_x = max(0, min(square_x, large_size - square_size))
    square_y = max(0, min(square_y, large_size - square_size))

    # 3. 绘制黑色正方形
    draw.rectangle(
        [square_x, square_y, square_x + square_size, square_y + square_size],
        fill=(0, 0, 0)
    )

    # 4. 计算数字大小（相对于正方形）
    digit_size = int(square_size * digit_size_ratio)
    font = FontSelector.load_pil_font(digit_size, font_cfg if font_cfg else FontConfig())

    # 5. 计算文字边界框
    bbox = draw.textbbox((0, 0), str(digit), font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_offset_x = bbox[0]
    text_offset_y = bbox[1]

    # 6. 在正方形中心绘制数字（固定中心，与placement.py一致）
    square_center_x = square_x + square_size // 2
    square_center_y = square_y + square_size // 2
    x = square_center_x - text_offset_x - text_w // 2
    y = square_center_y - text_offset_y - text_h // 2

    # 7. 绘制白色数字
    draw.text((x, y), str(digit), fill=(255, 255, 255), font=font)

    # 8. 模拟CV裁切（带误差）
    crop_x = square_x + random.randint(-cv_noise_level, cv_noise_level)
    crop_y = square_y + random.randint(-cv_noise_level, cv_noise_level)
    crop_size = square_size + random.randint(-cv_noise_level, cv_noise_level)

    # 确保裁切区域在图像内
    crop_x = max(0, min(crop_x, large_size - crop_size))
    crop_y = max(0, min(crop_y, large_size - crop_size))
    crop_size = min(crop_size, large_size - crop_x, large_size - crop_y)

    # 裁切图像
    img = img.crop((crop_x, crop_y, crop_x + crop_size, crop_y + crop_size))

    # 调整到目标大小
    img = img.resize((image_size, image_size), Image.LANCZOS)

    # 9. 模拟光照变化
    if lighting_variation:
        # 亮度调整
        if random.random() < 0.5:
            brightness_factor = random.uniform(0.7, 1.3)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(brightness_factor)

        # 对比度调整
        if random.random() < 0.5:
            contrast_factor = random.uniform(0.7, 1.3)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast_factor)

    # 10. 计算数字边界框（归一化到裁切后的图像）
    actual_x = x + text_offset_x - crop_x
    actual_y = y + text_offset_y - crop_y

    # 考虑resize的影响
    scale_x = image_size / crop_size
    scale_y = image_size / crop_size

    norm_cx = (actual_x + text_w / 2) * scale_x / image_size
    norm_cy = (actual_y + text_h / 2) * scale_y / image_size
    norm_w = text_w * scale_x / image_size
    norm_h = text_h * scale_y / image_size

    # 确保边界框在有效范围内
    norm_cx = max(0.0, min(1.0, norm_cx))
    norm_cy = max(0.0, min(1.0, norm_cy))
    norm_w = max(0.01, min(1.0, norm_w))
    norm_h = max(0.01, min(1.0, norm_h))

    return img, (norm_cx, norm_cy, norm_w, norm_h)


def _generate_noise_image(
    image_size: int,
    square_ratio: float = 0.8,
    cv_noise_level: int = 5,
    lighting_variation: bool = True,
) -> tuple[Image.Image, list]:
    """生成噪声样本（无数字的正方形）

    Args:
        image_size: 图片尺寸
        square_ratio: 正方形占大图的比例 (0-1)
        cv_noise_level: CV裁切误差（像素）
        lighting_variation: 是否模拟光照变化

    Returns:
        图片和空边界框列表
    """
    # 1. 创建大尺寸白色背景（包含边距）
    margin = random.randint(5, 20)  # 随机边距
    large_size = image_size + margin * 2
    img = Image.new("RGB", (large_size, large_size), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 2. 计算正方形区域（带随机偏移，模拟CV检测误差）
    square_size = int(large_size * square_ratio)
    square_x = (large_size - square_size) // 2 + random.randint(-cv_noise_level, cv_noise_level)
    square_y = (large_size - square_size) // 2 + random.randint(-cv_noise_level, cv_noise_level)

    # 确保正方形在图像内
    square_x = max(0, min(square_x, large_size - square_size))
    square_y = max(0, min(square_y, large_size - square_size))

    # 3. 绘制黑色正方形（无数字）
    draw.rectangle(
        [square_x, square_y, square_x + square_size, square_y + square_size],
        fill=(0, 0, 0)
    )

    # 4. 模拟CV裁切（带误差）
    crop_x = square_x + random.randint(-cv_noise_level, cv_noise_level)
    crop_y = square_y + random.randint(-cv_noise_level, cv_noise_level)
    crop_size = square_size + random.randint(-cv_noise_level, cv_noise_level)

    # 确保裁切区域在图像内
    crop_x = max(0, min(crop_x, large_size - crop_size))
    crop_y = max(0, min(crop_y, large_size - crop_size))
    crop_size = min(crop_size, large_size - crop_x, large_size - crop_y)

    # 裁切图像
    img = img.crop((crop_x, crop_y, crop_x + crop_size, crop_y + crop_size))

    # 调整到目标大小
    img = img.resize((image_size, image_size), Image.LANCZOS)

    # 5. 模拟光照变化
    if lighting_variation:
        # 亮度调整
        if random.random() < 0.5:
            brightness_factor = random.uniform(0.7, 1.3)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(brightness_factor)

        # 对比度调整
        if random.random() < 0.5:
            contrast_factor = random.uniform(0.7, 1.3)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast_factor)

    # 噪声样本没有标注
    return img, []


def _save_yolo_sample(
    yolo_dataset_dir: str,
    split: str,
    base_name: str,
    img: Image.Image,
    bboxes: list[tuple[int, float, float, float, float]],
    augment_cfg: AugmentConfig | None = None,
    augment: bool = False,
) -> None:
    """保存YOLO样本"""
    images_dir = os.path.join(yolo_dataset_dir, split, "images")
    labels_dir = os.path.join(yolo_dataset_dir, split, "labels")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    if augment and split == "train" and augment_cfg:
        img = _apply_augmentation(img, augment_cfg)

    dst_image = os.path.join(images_dir, f"{base_name}.png")
    img.save(dst_image)

    txt_path = os.path.join(labels_dir, f"{base_name}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for class_id, cx, cy, w, h in bboxes:
            f.write(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")


def generate_yolo_dataset(
    yolo_cfg: YoloExportConfig,
    yolo_dataset_dir: str,
    augment_cfg: AugmentConfig,
    font_cfg: FontConfig,
) -> None:
    """生成YOLO数据集（多尺度 + 随机占比 + 模拟CV误差 + 光照变化 + 多字体）"""
    if not yolo_cfg.enable:
        return

    init_yolo_dataset_dir(yolo_cfg, yolo_dataset_dir)

    digit_cfg = yolo_cfg.digit
    image_sizes = digit_cfg.image_sizes
    ratio_min = digit_cfg.digit_size_ratio_min
    ratio_max = digit_cfg.digit_size_ratio_max
    square_ratio = digit_cfg.square_ratio
    cv_noise_level = digit_cfg.cv_noise_level
    samples_per_digit = digit_cfg.samples_per_digit

    print(f"[bold cyan]=== 生成YOLO数据集 ({samples_per_digit}张/数字) ===[/bold cyan]")
    print(f"  模拟CV裁切图像，多尺度 {image_sizes}，数字占正方形 {ratio_min*100:.0f}%-{ratio_max*100:.0f}%，正方形占图片 {square_ratio*100:.0f}%")
    print(f"  数字位置随机，CV裁切误差 ±{cv_noise_level}px，光照变化，多字体")

    # 生成数字样本
    for digit in range(10):
        print(f"  生成数字 {digit}...", end=" ")
        count = 0

        for i in range(samples_per_digit):
            # 随机选择图片大小
            image_size = random.choice(image_sizes)
            # 随机选择数字占正方形的比例
            digit_size_ratio = random.uniform(ratio_min, ratio_max)

            # 生成图片（带CV误差、光照变化、多字体）
            img, bbox = _generate_digit_image(
                digit,
                image_size,
                digit_size_ratio,
                square_ratio,
                cv_noise_level,
                font_cfg,
                lighting_variation=True,
            )

            # 保存
            split = _get_split(yolo_cfg)
            base_name = f"digit_{digit}_{i:04d}"
            bboxes = [(digit, *bbox)]

            _save_yolo_sample(yolo_dataset_dir, split, base_name, img, bboxes, augment_cfg, augment=True)
            count += 1

        print(f"完成 ({count}张)")

    cleanup_yolo_tmp(yolo_dataset_dir)
    print("[bold green]YOLO数据集生成完毕![/bold green]")


def init_yolo_dataset_dir(yolo_cfg: YoloExportConfig, yolo_dataset_dir: str) -> None:
    """初始化YOLO数据集目录结构和data.yaml"""
    if not yolo_cfg.enable:
        return

    for split in ["train", "val", "test"]:
        os.makedirs(os.path.join(yolo_dataset_dir, split, "images"), exist_ok=True)
        os.makedirs(os.path.join(yolo_dataset_dir, split, "labels"), exist_ok=True)

    class_names = [str(i) for i in range(10)]

    data = {
        "path": os.path.abspath(yolo_dataset_dir).replace("\\", "/"),
        "train": "train/images",
        "val": "val/images",
        "test": "test/images",
        "nc": len(class_names),
        "names": class_names,
    }

    yaml_path = os.path.join(yolo_dataset_dir, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def cleanup_yolo_tmp(yolo_dataset_dir: str) -> None:
    """清理临时目录"""
    tmp_dir = os.path.join(yolo_dataset_dir, "_tmp")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)
