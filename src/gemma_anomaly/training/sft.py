"""QLoRA supervised fine tuning configuration.

Every value below is a starting candidate, not an established optimum. Validate
a gradient update and a saved then reloaded adapter before committing to a long
run. Choose max_seq_length from measured token counts, not from this file.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrainingConfig:
    base_model: str = ""          # pin the exact revision after a compatibility test
    revision: str = ""
    load_in_4bit: bool = True
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj",
    ])
    learning_rate: float = 1e-4
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 16
    num_train_epochs: float = 1.0
    max_seq_length: int = 2048    # set from measured token counts
    completion_only_loss: bool = True
    warmup_ratio: float = 0.03
    logging_steps: int = 10
    save_steps: int = 100
    seed: int = 17
    output_dir: str = "artifacts/adapter"

    def provisional_notes(self) -> list[str]:
        return [
            "lora_r, learning_rate, and epochs are tuning candidates.",
            "max_seq_length must come from measured token counts and memory.",
            "Run a smoke job first and record memory and examples per second.",
            "Training and serving on one GPU compete for memory. Stage them sequentially.",
        ]


def build_trainer(config: TrainingConfig, train_path: str, val_path: str):
    """Wire Transformers, PEFT, and TRL SFTTrainer.

    Left unimplemented on purpose. It must be written against the pinned Gemma
    revision and the measured memory on the allocated GPU, using the model's own
    chat template and completion only loss.
    """
    raise NotImplementedError(
        "Implement after the checkpoint revision is pinned and a smoke run has "
        "measured memory and throughput on the allocated Lambda instance."
    )


def smoke_run(config: TrainingConfig) -> dict:
    """Short run to measure peak memory and examples per second before the real job."""
    raise NotImplementedError("Run on the GPU instance, not on the Mac.")
