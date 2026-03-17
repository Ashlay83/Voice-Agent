

# 2. Mount your Google Drive so Colab can access your files
from google.colab import drive
drive.mount('/content/drive')

# 3. Load your brand new dataset!
from datasets import load_dataset

# We use 'audiofolder' which automatically looks for your metadata.csv and .wav files
print("\nLoading dataset from Drive...")
dataset = load_dataset("audiofolder", data_dir="/content/drive/MyDrive/whisper_malayalam_dataset")

# 4. Print the result to make sure it worked
print("\nSuccess! Here is what your dataset looks like to the AI:")
print(dataset)

# 1. Install the transformers library and audio processing tools
!pip install transformers librosa soundfile

# 2. Load the Whisper Processor
from transformers import WhisperProcessor

print("Downloading the Whisper Processor...")
processor = WhisperProcessor.from_pretrained("openai/whisper-medium", language="Malayalam", task="translate")

print("Processor loaded successfully!")

from datasets import Audio

# 1. Force all audio to exactly 16kHz so Whisper can understand it
dataset = dataset.cast_column("audio", Audio(sampling_rate=16000))

# 2. Create the translation function
def prepare_dataset(batch):
    # Get the raw audio array
    audio = batch["audio"]

    # Process Audio: Convert the sound wave into a visual map of frequencies
    batch["input_features"] = processor.feature_extractor(audio["array"], sampling_rate=audio["sampling_rate"]).input_features[0]

    # Process Text: Convert the English sentence into token IDs (numbers)
    batch["labels"] = processor.tokenizer(batch["transcription"]).input_ids

    return batch

# 3. Apply this function to your 15 examples
print("Converting audio and text into numbers...")

processed_dataset = dataset.map(prepare_dataset, remove_columns=dataset.column_names["train"], num_proc=1)

print("Dataset processing complete!")

import torch
from transformers import WhisperForConditionalGeneration, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model

print("\nSetting up 8-bit compression...")
# 1. Create the new quantization config
bnb_config = BitsAndBytesConfig(load_in_8bit=True)

print("Loading the base Whisper model (this might take a minute)...")
# 2. Pass the config object instead of the old keyword argument
model = WhisperForConditionalGeneration.from_pretrained(
    "openai/whisper-medium",
    quantization_config=bnb_config,
    device_map="auto"
)

# 3. Hardcode the instructions: Tell it to translate Malayalam to English
model.config.forced_decoder_ids = processor.get_decoder_prompt_ids(language="Malayalam", task="translate")
model.config.suppress_tokens = []

# 4. Configure the LoRA Adapter
lora_config = LoraConfig(
    r=32,
    lora_alpha=64,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    bias="none"
)

# 5. Attach the adapter to the model
model = get_peft_model(model, lora_config)

print("\nSuccess! The model is loaded and the LoRA adapter is attached.")
model.print_trainable_parameters()

import torch
from dataclasses import dataclass
from typing import Any, Dict, List, Union
from transformers import Seq2SeqTrainingArguments, Seq2SeqTrainer

print("1. Building the Data Collator (Padder)...")
@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    processor: Any

    def __call__(self, features: List[Dict[str, Union[List[int], torch.Tensor]]]) -> Dict[str, torch.Tensor]:
        # Pad the audio features
        input_features = [{"input_features": feature["input_features"]} for feature in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

        # Pad the text labels
        label_features = [{"input_ids": feature["labels"]} for feature in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")

        # Replace padding with -100 so the model ignores the blank spaces during training
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)

        # Clean up beginning-of-sequence tokens
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch

data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)

print("2. Setting up Training Rules...")
# Tell the trainer exactly how to learn
training_args = Seq2SeqTrainingArguments(
    output_dir="/content/drive/MyDrive/whisper_malayalam_dataset/whisper-lora-model",  # Save directly to your Drive!
    per_device_train_batch_size=4,   # Train 4 examples at a time
    learning_rate=1e-3,              # The LoRA learning speed
    num_train_epochs=15,             # Read through your 15 examples 15 times
    fp16=True,                       # Use 16-bit math to speed up the GPU
    logging_steps=5,                 # Print an update every 5 steps
    remove_unused_columns=False,     # Keep all Whisper columns
    label_names=["labels"],
)

print("3. Initializing Trainer...")
trainer = Seq2SeqTrainer(
    args=training_args,
    model=model,
    train_dataset=processed_dataset["train"],
    data_collator=data_collator,

)

print("\n🚀 STARTING TRAINING 🚀")
# This is the command that actually makes the AI learn!
trainer.train()

print("\n✅ Training Complete! Saving your custom adapter to Google Drive...")
trainer.model.save_pretrained("/content/drive/MyDrive/whisper_malayalam_dataset/whisper-lora-model")
print("Adapter saved successfully!")

import torch
from peft import PeftModel
from transformers import WhisperForConditionalGeneration

print("1. Loading base model (without 8-bit compression so we can merge cleanly)...")
base_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-medium", device_map="cpu")

print("2. Attaching your custom LoRA adapter...")
# We point it to the adapter you just saved in your Drive
model = PeftModel.from_pretrained(base_model, "/content/drive/MyDrive/whisper_malayalam_dataset/whisper-lora-model")

print("3. Merging the adapter permanently into the base brain...")
merged_model = model.merge_and_unload()

print("4. Saving the complete, unified model to Drive...")
merged_model.save_pretrained("/content/drive/MyDrive/whisper_malayalam_dataset/whisper-merged")
processor.save_pretrained("/content/drive/MyDrive/whisper_malayalam_dataset/whisper-merged")

print("✅ Merged model saved successfully!")

from huggingface_hub import hf_hub_download
import shutil

print("1. Fetching missing config files from OpenAI...")
repo_id = "openai/whisper-medium"
merged_folder = "/content/drive/MyDrive/whisper_malayalam_dataset/whisper-merged"

# Download preprocessor_config.json and tokenizer.json and place them in your merged folder
prep_path = hf_hub_download(repo_id=repo_id, filename="preprocessor_config.json")
shutil.copy(prep_path, f"{merged_folder}/preprocessor_config.json")

tok_path = hf_hub_download(repo_id=repo_id, filename="tokenizer.json")
shutil.copy(tok_path, f"{merged_folder}/tokenizer.json")

print("✅ Missing files added successfully!")
print("\n2. Running CTranslate2 Converter...")

# Now the converter will find everything it needs!
!ct2-transformers-converter --model /content/drive/MyDrive/whisper_malayalam_dataset/whisper-merged \
    --output_dir /content/drive/MyDrive/whisper_malayalam_dataset/faster-whisper-malayalam \
    --quantization int8 \
    --copy_files tokenizer.json preprocessor_config.json