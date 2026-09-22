"""Train a local LoRA adapter using approved CV labels only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from training.dataset import INSTRUCTION, validated_examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/training'))
    parser.add_argument('--base-model', type=Path, required=True, help='Local Hugging Face model folder, not an Ollama blob')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--max-length', type=int, default=4096)
    args = parser.parse_args()
    train, validation = validated_examples(args.data)
    if len(train) < 20 or len(validation) < 5:
        raise SystemExit(f'Need at least 20 approved training and 5 approved held-out examples; found {len(train)} and {len(validation)}. Draft answers cannot train the model.')
    if not args.base_model.is_dir():
        raise SystemExit('Download a compatible Hugging Face base model locally first.')
    if args.output.exists():
        raise SystemExit('Choose a new output directory to preserve existing runs.')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_DATASETS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, DataCollatorForSeq2Seq
    from peft import LoraConfig, get_peft_model
    if not torch.cuda.is_available():
        raise SystemExit('This training configuration needs an NVIDIA CUDA GPU. No weights were trained.')
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
    tokenizer.pad_token = tokenizer.eos_token

    def encode(rows):
        encoded = []
        for row in rows:
            messages = [{'role': 'system', 'content': INSTRUCTION}, {'role': 'user', 'content': 'Reference date: ' + row['reference_date'] + '\nCV:\n' + row['text']}]
            prefix = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
            messages.append({'role': 'assistant', 'content': json.dumps(row['answers'], ensure_ascii=False)})
            tokens = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
            if tokens[:len(prefix)] != prefix:
                raise ValueError('Chat template prefix mismatch; refusing to train on prompt tokens.')
            if len(tokens) > args.max_length:
                raise ValueError(f"{row['id']}: CV exceeds max-length. Review a focused source excerpt or use a larger context; no silent truncation.")
            encoded.append({'input_ids': tokens, 'attention_mask': [1] * len(tokens), 'labels': [-100] * len(prefix) + tokens[len(prefix):]})
        return encoded

    train_tokens, eval_tokens = encode(train), encode(validation)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.base_model, local_files_only=True, torch_dtype=dtype)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(task_type='CAUSAL_LM', r=8, lora_alpha=16, lora_dropout=0.05, target_modules=['q_proj', 'v_proj']))
    model.enable_input_require_grads()
    args.output.mkdir(parents=True)
    training_args = TrainingArguments(
        output_dir=str(args.output), num_train_epochs=args.epochs,
        per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=8, gradient_checkpointing=True,
        learning_rate=1e-4, logging_steps=1, eval_strategy='epoch', save_strategy='epoch',
        save_total_limit=2, report_to='none', push_to_hub=False, seed=42,
        bf16=dtype == torch.bfloat16, fp16=dtype == torch.float16)
    trainer = Trainer(model=model, args=training_args, train_dataset=train_tokens, eval_dataset=eval_tokens,
                      processing_class=tokenizer, data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100))
    baseline = trainer.evaluate()
    trainer.train()
    final = trainer.evaluate()
    trainer.save_model(str(args.output / 'adapter'))
    tokenizer.save_pretrained(str(args.output / 'adapter'))
    (args.output / 'metrics.json').write_text(json.dumps({'baseline': baseline, 'final': final,
        'train_examples': len(train), 'held_out_examples': len(validation),
        'note': 'Loss metrics only. Field accuracy must be checked before production deployment.'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
