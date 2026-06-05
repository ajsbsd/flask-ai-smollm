#!/usr/bin/env python3
import re

filepath = "./qwen2.5-1.5B-Instruct-gdk-demo.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

fixed = []
for i, line in enumerate(lines, 1):
    # Remove trailing whitespace (W291, W293)
    line = line.rstrip() + "\n"
    
    # Fix unused global on line 187
    if i == 187 and "global tokenizer, llm_model" in line:
        line = "    # Models loaded at module level; accessed read-only here\n"
    
    # Fix unused global on line 273  
    elif i == 273 and "global whisper_processor" in line:
        line = "    # Whisper models loaded at module level; accessed read-only here\n"
    
    # Fix long line 234
    elif i == 234 and "apply_chat_template" in line and len(line) > 120:
        line = """    input_text = tokenizer.apply_chat_template(
        messages, 
        tokenize=False, 
        add_generation_prompt=True
    )
"""
    
    fixed.append(line)

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(fixed)

print("✅ Fixed F824, W291, W293, E501 errors")
