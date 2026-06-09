from __future__ import annotations

import os
import random
import tomllib
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import NamedTuple


# ===== 配置加载（仅 __main__ 调用） =====


def load_config(path: Path | None = None) -> dict:
    """读取 config.toml. 仅在 __main__ 入口调用，不再有模块级副作用."""
    if path is not None:
        candidates = [path]
    else:
        candidates = [
            Path.cwd() / "config.toml",
            Path(__file__).resolve().parent.parent.parent / "config.toml",
        ]
    for p in candidates:
        if p.exists():
            with open(p, "rb") as f:
                return tomllib.load(f)
    raise FileNotFoundError(
        f"config.toml not found. Searched: {[str(c) for c in candidates]}"
    )


# ===== 难度枚举 =====


class Difficulty(IntEnum):
    """发挥目标物难度级别"""

    EASY = 0  # 1-3个正方形，不旋转，不重叠，平均分布
    MEDIUM = 1  # 2-4个正方形，不旋转，最多1对重叠，其余留间距
    HARD = 2  # 3-5个正方形，随机旋转，可重叠

    @property
    def min_count(self) -> int:
        return {0: 1, 1: 2, 2: 3}[self.value]

    @property
    def max_count(self) -> int:
        return {0: 3, 1: 4, 2: 5}[self.value]


# ===== 全局配置 =====


@dataclass(frozen=True)
class GlobalConfig:
    output_dir: str = "output"

    @classmethod
    def from_raw(cls, raw: dict) -> GlobalConfig:
        global_cfg = raw.get("global", {})
        return cls(
            output_dir=global_cfg.get("output_dir", "output"),
        )


# ===== 页面配置 =====


@dataclass(frozen=True)
class PageConfig:
    width_mm: float = 210.0
    height_mm: float = 297.0
    margin: float = 20.0
    safe_margin: float = 5.0

    @property
    def inner_x(self) -> float:
        return self.margin + self.safe_margin

    @property
    def inner_y(self) -> float:
        return self.margin + self.safe_margin

    @property
    def inner_width(self) -> float:
        return self.width_mm - 2 * self.margin - 2 * self.safe_margin

    @property
    def inner_height(self) -> float:
        return self.height_mm - 2 * self.margin - 2 * self.safe_margin

    @classmethod
    def from_raw(cls, raw: dict) -> PageConfig:
        pg = raw["page"]
        return cls(
            width_mm=pg["width_mm"],
            height_mm=pg["height_mm"],
            margin=pg["margin_mm"],
            safe_margin=pg["safe_margin_mm"],
        )


# ===== 基本目标物配置 =====


@dataclass(frozen=True)
class BasicTargetConfig:
    enable: bool = True
    min_size_mm: int = 100
    max_size_mm: int = 160
    step_mm: int = 5

    @classmethod
    def from_raw(cls, raw: dict) -> BasicTargetConfig:
        cfg = raw["basic_target"]
        return cls(
            enable=cfg["enable"],
            min_size_mm=cfg["min_size_mm"],
            max_size_mm=cfg["max_size_mm"],
            step_mm=cfg["step_mm"],
        )


# ===== 发挥目标物配置 =====


@dataclass(frozen=True)
class SquareConfig:
    min_size_mm: int = 60
    max_size_mm: int = 120
    gap_mm: float = 10.0

    @classmethod
    def from_raw(cls, raw: dict) -> SquareConfig:
        sq = raw["extended_target"]["square"]
        return cls(
            min_size_mm=sq["min_size_mm"],
            max_size_mm=sq["max_size_mm"],
            gap_mm=sq["gap_mm"],
        )


@dataclass(frozen=True)
class DigitConfig:
    font_size: int = 30
    overlap_threshold_mm: float = 40.0

    @classmethod
    def from_raw(cls, raw: dict) -> DigitConfig:
        dg = raw["extended_target"]["digit"]
        return cls(
            font_size=dg["font_size"], overlap_threshold_mm=dg["overlap_threshold_mm"]
        )


# ===== 字体配置 =====


class FontEntry(NamedTuple):
    display_name: str
    folder_name: str
    css_regular: str
    css_bold: str
    font_file: str


DEFAULT_FONT_CONFIGS: dict[str, FontEntry] = {
    "Times New Roman": FontEntry(
        display_name="Times New Roman",
        folder_name="Times_New_Roman",
        css_regular="Times New Roman, Times, serif",
        css_bold="Times New Roman, Times, serif",
        font_file="fonts/times.ttf",
    ),
    "Arial": FontEntry(
        display_name="Arial",
        folder_name="Arial",
        css_regular="Arial, Helvetica, sans-serif",
        css_bold="Arial, Helvetica, sans-serif",
        font_file="fonts/arial.ttf",
    ),
    "Consolas": FontEntry(
        display_name="Consolas",
        folder_name="Consolas",
        css_regular="Consolas, Courier New, monospace",
        css_bold="Consolas, Courier New, monospace",
        font_file="fonts/consolas.ttf",
    ),
}


@dataclass(frozen=True)
class FontConfig:
    """纯配置数据，不包含行为逻辑"""

    configs: dict[str, FontEntry] = field(
        default_factory=lambda: dict(DEFAULT_FONT_CONFIGS)
    )
    weights: dict[str, float] = field(default_factory=lambda: {"Times New Roman": 1.0})
    bold_probability: float = 0.3
    enable_bold: bool = False
    enable_multi_font: bool = False
    font_paths: tuple[str, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict) -> FontConfig:
        font_raw = raw.get("fonts", {})
        enable_multi = font_raw.get("enable_multi_font", False)
        enable_bold = font_raw.get("enable_bold", False)
        bold_prob = font_raw.get("bold_probability", 0.3)
        font_paths = tuple(font_raw.get("paths", []))

        if enable_multi:
            raw_weights = font_raw.get("weights", {})
            weights = (
                dict(raw_weights)
                if raw_weights
                else {"Times New Roman": 0.6, "Arial": 0.2, "Consolas": 0.2}
            )
        else:
            weights = {"Times New Roman": 1.0}

        return cls(
            configs=dict(DEFAULT_FONT_CONFIGS),
            weights=weights,
            bold_probability=bold_prob,
            enable_bold=enable_bold,
            enable_multi_font=enable_multi,
            font_paths=font_paths,
        )


class FontSelector:
    """字体选择行为 — 纯函数集合，接收 FontConfig"""

    @staticmethod
    def choose_font(cfg: FontConfig) -> tuple[str, FontEntry]:
        names = list(cfg.weights.keys())
        values = list(cfg.weights.values())
        chosen = random.choices(names, weights=values, k=1)[0]
        return chosen, cfg.configs[chosen]

    @staticmethod
    def should_use_bold(cfg: FontConfig) -> bool:
        if not cfg.enable_bold:
            return False
        return random.random() < cfg.bold_probability

    @staticmethod
    def get_css_font(entry: FontEntry, use_bold: bool) -> str:
        return entry.css_bold if use_bold else entry.css_regular

    @staticmethod
    def get_folder_name(entry: FontEntry, use_bold: bool) -> str:
        suffix = "_Bold" if use_bold else ""
        return f"{entry.folder_name}{suffix}"

    @staticmethod
    def load_pil_font(font_size: int, cfg: FontConfig):
        from PIL import ImageFont

        _, entry = FontSelector.choose_font(cfg)
        font_path = entry.font_file

        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                pass

        for entry in cfg.configs.values():
            if os.path.exists(entry.font_file):
                try:
                    return ImageFont.truetype(entry.font_file, font_size)
                except Exception:
                    continue

        return ImageFont.load_default()


# ===== 数据增强配置 =====


@dataclass(frozen=True)
class AugmentConfig:
    """全局数据增强配置"""

    enable: bool = True
    rotation_range: float = 5.0
    brightness_range: tuple[float, float] = (0.9, 1.1)
    contrast_range: tuple[float, float] = (0.9, 1.1)
    noise_std: float = 0.005

    @classmethod
    def from_raw(cls, raw: dict) -> AugmentConfig:
        aug = raw.get("augment", {})
        return cls(
            enable=aug.get("enable", True),
            rotation_range=aug.get("rotation_range", 5.0),
            brightness_range=tuple(aug.get("brightness_range", [0.9, 1.1])),
            contrast_range=tuple(aug.get("contrast_range", [0.9, 1.1])),
            noise_std=aug.get("noise_std", 0.005),
        )


# ===== 发挥目标物总配置 =====


@dataclass(frozen=True)
class ExtendedTargetConfig:
    enable: bool = True
    difficulty: Difficulty = Difficulty.MEDIUM
    total_files: int = 50
    digits_per_square: bool = True
    square: SquareConfig = field(default_factory=SquareConfig)
    digit: DigitConfig = field(default_factory=DigitConfig)

    @property
    def min_count(self) -> int:
        return self.difficulty.min_count

    @property
    def max_count(self) -> int:
        return self.difficulty.max_count

    @classmethod
    def from_raw(cls, raw: dict) -> ExtendedTargetConfig:
        ext = raw["extended_target"]
        return cls(
            enable=ext["enable"],
            difficulty=Difficulty(ext["difficulty"]),
            total_files=ext["total_files"],
            digits_per_square=ext.get("digits_per_square", True),
            square=SquareConfig.from_raw(raw),
            digit=DigitConfig.from_raw(raw),
        )


# ===== C 题标准模式配置 =====


@dataclass(frozen=True)
class CExamTypeConfig:
    """单个 C 题发挥目标物类型的配置"""

    count: int | None = None
    count_min: int | None = None
    count_max: int | None = None
    total_files: int = 3
    generate_digits: bool = False
    allow_overlap: bool = False
    allow_rotation: bool = False

    @property
    def effective_min(self) -> int:
        return self.count if self.count is not None else (self.count_min or 1)

    @property
    def effective_max(self) -> int:
        return self.count if self.count is not None else (self.count_max or 3)


@dataclass(frozen=True)
class CExamConfig:
    enable: bool = False
    type1_single: CExamTypeConfig = field(
        default_factory=lambda: CExamTypeConfig(count=1, total_files=3)
    )
    type2_multi: CExamTypeConfig = field(
        default_factory=lambda: CExamTypeConfig(
            count_min=2, count_max=4, total_files=5, allow_overlap=True
        )
    )
    type3_digit: CExamTypeConfig = field(
        default_factory=lambda: CExamTypeConfig(
            count_min=2,
            count_max=4,
            total_files=5,
            generate_digits=True,
            allow_overlap=True,
        )
    )
    type4_rotated: CExamTypeConfig = field(
        default_factory=lambda: CExamTypeConfig(
            count=1, total_files=5, allow_rotation=True
        )
    )

    @classmethod
    def from_raw(cls, raw: dict) -> CExamConfig:
        if "c_exam" not in raw:
            return cls()
        ce = raw["c_exam"]

        def _parse_type(key: str, defaults: dict) -> CExamTypeConfig:
            if key not in ce:
                return CExamTypeConfig(**defaults)
            t = ce[key]
            return CExamTypeConfig(
                count=t.get("count"),
                count_min=t.get("count_min"),
                count_max=t.get("count_max"),
                total_files=t.get("total_files", defaults.get("total_files", 3)),
                generate_digits=t.get(
                    "generate_digits", defaults.get("generate_digits", False)
                ),
                allow_overlap=t.get(
                    "allow_overlap", defaults.get("allow_overlap", False)
                ),
                allow_rotation=t.get(
                    "allow_rotation", defaults.get("allow_rotation", False)
                ),
            )

        return cls(
            enable=ce.get("enable", False),
            type1_single=_parse_type("type1_single", {"count": 1, "total_files": 3}),
            type2_multi=_parse_type(
                "type2_multi",
                {
                    "count_min": 2,
                    "count_max": 4,
                    "total_files": 5,
                    "allow_overlap": True,
                },
            ),
            type3_digit=_parse_type(
                "type3_digit",
                {
                    "count_min": 2,
                    "count_max": 4,
                    "total_files": 5,
                    "generate_digits": True,
                    "allow_overlap": True,
                },
            ),
            type4_rotated=_parse_type(
                "type4_rotated", {"count": 1, "total_files": 5, "allow_rotation": True}
            ),
        )


# ===== 导出配置 =====


@dataclass(frozen=True)
class ExportConfig:
    png_size: int = 60
    enable_digit_export: bool = False

    @classmethod
    def from_raw(cls, raw: dict) -> ExportConfig:
        exp = raw["export"]
        return cls(
            png_size=exp["png_size"], enable_digit_export=exp["enable_digit_export"]
        )


@dataclass(frozen=True)
class YoloDigitConfig:
    """YOLO数字裁剪配置"""

    image_sizes: tuple[int, ...] = (64, 128, 256)
    digit_size_ratio_min: float = 0.25
    digit_size_ratio_max: float = 0.5
    square_ratio: float = 0.8
    cv_noise_level: int = 5
    samples_per_digit: int = 1000

    @classmethod
    def from_raw(cls, raw: dict) -> YoloDigitConfig:
        digit_raw = raw.get("yolo_export", {}).get("digit", {})
        return cls(
            image_sizes=tuple(digit_raw.get("image_sizes", [64, 128, 256])),
            digit_size_ratio_min=digit_raw.get("digit_size_ratio_min", 0.25),
            digit_size_ratio_max=digit_raw.get("digit_size_ratio_max", 0.5),
            square_ratio=digit_raw.get("square_ratio", 0.8),
            cv_noise_level=digit_raw.get("cv_noise_level", 5),
            samples_per_digit=digit_raw.get("samples_per_digit", 1000),
        )


@dataclass(frozen=True)
class YoloExportConfig:
    """YOLO数据集导出配置"""

    enable: bool = False
    train_ratio: float = 0.8
    val_ratio: float = 0.15
    test_ratio: float = 0.05
    digit: YoloDigitConfig = field(default_factory=YoloDigitConfig)

    @classmethod
    def from_raw(cls, raw: dict) -> YoloExportConfig:
        if "yolo_export" not in raw:
            return cls()
        yolo = raw["yolo_export"]

        return cls(
            enable=yolo.get("enable", False),
            train_ratio=yolo.get("train_ratio", 0.8),
            val_ratio=yolo.get("val_ratio", 0.15),
            test_ratio=yolo.get("test_ratio", 0.05),
            digit=YoloDigitConfig.from_raw(raw),
        )


@dataclass(frozen=True)
class NoiseConfig:
    enable: bool = False
    count: int = 4
    overlap_threshold: float = 0.4
    crop_size_mm: float = 50.0
    max_attempts_factor: int = 500

    @classmethod
    def from_raw(cls, raw: dict) -> NoiseConfig:
        n = raw["export"]["noise"]
        return cls(
            enable=n["enable"],
            count=n["count"],
            overlap_threshold=n["overlap_threshold"],
            crop_size_mm=n["crop_size_mm"],
            max_attempts_factor=n.get("max_attempts_factor", 500),
        )
