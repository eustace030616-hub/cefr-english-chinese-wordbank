"""
MiniMax Translation Script with Checkpoint/Resume
Generates examples and translates to Chinese in batches
Checkpoint contains full results - will retry incomplete batches on resume
"""

import json
import re
import requests
import time
import os

# ============ CONFIGURATION ============
API_KEY = ""
MODEL = "MiniMax-M2.5-highspeed"
API_URL = ""
# =====================================

INPUT_FILE = " "
OUTPUT_FILE = " "
CHECKPOINT_FILE = " "
BATCH_SIZE = 25


def reached_limit(error_msg):
    """Check if error indicates rate limit or quota exceeded"""
    error_lower = error_msg.lower()
    keywords = [
        "rate limit",
        "quota",
        "exceeded",
        "too many",
        "limit reached",
        "429",
        "403",
        "402",
        "billing",
        "token limit",
        "max retries"
    ]
    return any(kw in error_lower for kw in keywords)


def translate_batch(prompt_text, batch_num):
    """Send batch to MiniMax API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "name": "MiniMax AI"
            },
            {
                "role": "user",
                "content": prompt_text
            }
        ]
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=120)

        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            elif "reply" in data and data["reply"]:
                return data["reply"]

        # Check for rate limit
        error_msg = response.text
        if reached_limit(error_msg):
            print(f"  [RATE LIMIT DETECTED]")
            return "RATE_LIMIT"

        print(f"  HTTP {response.status_code}: {response.text[:150]}")
        return None

    except Exception as e:
        if reached_limit(str(e)):
            print(f"  [RATE LIMIT DETECTED: {e}]")
            return "RATE_LIMIT"
        print(f"  Error: {e}")
        return None


def generate_examples_and_translate(words_batch, batch_num):
    """Generate English examples and translate to Chinese in one batch"""
    words_text = "\n".join([
        f"{j+1}. {w['word']}" for j, w in enumerate(words_batch)
    ])

    output_format = '{"word": "[Chinese]", "example_en": "[English]", "example_zh": "[Chinese]"}'

    prompt = f"""You are a dictionary compiler. For each word below:
1. Create a simple English example sentence
2. Translate the word and sentence to Simplified Chinese

Output format for EACH word (strictly follow this format, one per line):
{output_format}

Words to process:
{words_text}

Output (one per line):"""

    response = translate_batch(prompt, batch_num)
    return response


def parse_batch_response(response_text, words_batch):
    """Parse the API response - one JSON per line - and return list of results"""
    results = []
    lines = response_text.strip().split("\n")

    # Parse each line as a separate JSON object
    parsed_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to find and parse JSON object on this line
        try:
            start_brace = line.find("{")
            end_brace = line.rfind("}")
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                json_str = line[start_brace:end_brace+1]
                parsed = json.loads(json_str)
                parsed_lines.append(parsed)
            elif "not found" in line.lower() or "no translation" in line.lower():
                parsed_lines.append({"word": "", "example_en": "", "example_zh": ""})
        except:
            # If parsing fails, try to extract with regex
            word_match = re.search(r'"word"\s*:\s*"([^"]*)"', line)
            example_en_match = re.search(r'"example_en"\s*:\s*"([^"]*)"', line)
            example_zh_match = re.search(r'"example_zh"\s*:\s*"([^"]*)"', line)

            if word_match or example_en_match or example_zh_match:
                parsed_lines.append({
                    "word": word_match.group(1) if word_match else "",
                    "example_en": example_en_match.group(1) if example_en_match else "",
                    "example_zh": example_zh_match.group(1) if example_zh_match else ""
                })

    # Assign parsed results to words
    for i, word_obj in enumerate(words_batch):
        word = word_obj["word"]
        level = word_obj["level"]
        index = word_obj["index"]

        # Default values
        word_zh = ""
        example_en = ""
        example_zh = ""

        # Get parsed result for this position
        if i < len(parsed_lines):
            parsed = parsed_lines[i]
            word_zh = parsed.get("word", "")
            example_en = parsed.get("example_en", "")
            example_zh = parsed.get("example_zh", "")

        results.append({
            "word": word,
            "level": level,
            "word_zh": word_zh,
            "example_en": example_en,
            "example_zh": example_zh,
            "index": index
        })

    return results


def is_batch_complete(batch_results):
    """Check if all words in batch have valid translations"""
    for r in batch_results:
        if not r.get("word_zh") or not r.get("example_en") or not r.get("example_zh"):
            return False
    return True


def is_translation_valid(r):
    # check if got Empty reply
    if not r.get("word_zh") or not r.get("example_en") or not r.get("example_zh"):
        return False

    # Chinese check
    if not any('\u4e00' <= c <= '\u9fff' for c in r["word_zh"]):
        return False

    if not any('\u4e00' <= c <= '\u9fff' for c in r["example_zh"]):
        return False

    # English check
    if not any(c.isalpha() for c in r["example_en"]):
        return False

    return True


def save_checkpoint(results, checkpoint_file):
    """Save checkpoint with all results"""
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)


def load_checkpoint(checkpoint_file):
    """Load checkpoint and return results, or empty list"""
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("results", [])
    return []


def process_words():
    """Main processing function with checkpoint/resume"""
    # Load wordbank
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        content = content.replace("module.exports =", "").strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            content = content[start:end].rstrip(";")
        data = json.loads(content)

    words = data["words"]
    total = len(words)

    # Load checkpoint
    checkpoint_results = load_checkpoint(CHECKPOINT_FILE)
    processed_count = len(checkpoint_results)

    # Find where we are - filter out None entries
    valid_checkpoint_results = [r for r in checkpoint_results if r is not None]
    processed_words_set = set(r["word"] for r in valid_checkpoint_results)
    results = []

    # Skip already processed words, but validate their translations
    for w in words:
        if w["word"] in processed_words_set:
            # Find the saved result
            saved = next((r for r in valid_checkpoint_results if r["word"] == w["word"]), None)
            if is_translation_valid(saved) is True:
                # Valid saved result - keep it
                results.append(saved)
            else:
                print(f"invalid translation detected, will retry on next run")
                results.append(None)
        else:
            results.append(None)

    # Count valid results
    valid_count = sum(1 for r in results if r is not None)
    print(f"Total words: {total}")
    print(f"Valid from checkpoint: {valid_count}")
    print(f"Need to process: {total - valid_count}")
    print("=" * 60)

    start_time = time.time()
    last_save = time.time()

    # Process unprocessed words
    for i in range(total):
        if results[i] is not None:
            # Already processed with valid data
            continue

        batch_start = i
        batch_words = []
        batch_indices = []

        # Collect batch
        while len(batch_words) < BATCH_SIZE and i < total:
            if results[i] is None:
                batch_words.append(words[i])
                batch_indices.append(i)
            i += 1

        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"\nBatch {batch_num}/{total_batches} ({batch_start+1}-{batch_start+len(batch_words)}):")

        response_text = generate_examples_and_translate(batch_words, batch_num)

        if response_text == "RATE_LIMIT":
            # Save checkpoint and stop
            print(f"\n{'='*60}")
            print(f"RATE LIMIT REACHED at word {batch_start+1}")
            print("Checkpoint saved. Run script again to resume.")
            save_checkpoint(results, CHECKPOINT_FILE)
            return

        if response_text:
            print(f"  Response preview: {response_text[:500]}...")
            batch_results = parse_batch_response(response_text, batch_words)

            # Check if all translations are valid
            unchecked_translations = sum(1 for r in batch_results if r.get("word_zh") and r.get("example_en") and r.get("example_zh"))
            if is_translation_valid(unchecked_translations) is True:
                valid_translations = unchecked_translations
                print(f"  Valid translations: {valid_translations}/{len(batch_results)}")
            else:
                 # Some invalid - mark all for retry, don't save checkpoint
                  print(f"  Some translations invalid, will retry this batch")
                  batch_results = [None] * len(batch_words)  # Mark all for retry
            # Store results
            for j, idx in enumerate(batch_indices):
                results[idx] = batch_results[j]

            # Only save checkpoint if batch is successful
            if is_batch_complete(batch_results):
                save_checkpoint(results, CHECKPOINT_FILE)
                print(f"  [Checkpoint saved]")

        else:
            print(f"  Batch failed, will retry")
            # Mark as None so it retries
            for idx in batch_indices:
                results[idx] = None

        elapsed = time.time() - start_time
        current_valid = sum(1 for r in results if r is not None and r.get("word_zh"))
        progress = (current_valid / total * 100)
        eta = (total - current_valid) * (elapsed / current_valid) if current_valid else 0
        print(f"  Progress: {current_valid}/{total} ({progress:.1f}%) | ETA: {eta/60:.1f}min")

        # Small delay between batches
        time.sleep(0.5)

    # Final save - only keep valid results
    final_results = [r for r in results if r is not None and r.get("word_zh")]

    final_data = {
        "count": len(final_results),
        "words": final_results
    }

    # Save checkpoint with only valid results (no None)
    save_checkpoint(final_results, CHECKPOINT_FILE)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("module.exports = ")
        json.dump(final_data, f, ensure_ascii=False, indent=2)
        f.write(";")

    # Remove checkpoint if complete
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"DONE! {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"Saved to: {OUTPUT_FILE}")
    print(f"Final count: {len(final_results)}/{total}")


if __name__ == "__main__":
    process_words()
