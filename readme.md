# CEFR Wordbank

CEFR leveled word bank with English to Chinese translation and example sentences with translations.

## Data Sources

The raw word lists are based on:
- **CEFR-J Wordlist Version 1.5** — Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from http://www.cefr-j.org/download.html on 1/20/2020.
- **CEFR-J Grammar Profile Version 20180315** — Retrieved from http://www.cefr-j.org/download.html on 1/20/2020.

## Translation Process

`translate.py` uses the Minimax API to translate words in batches.

### How it works

1. Words are sent to the API in batches (25 words per request)
2. API responses are validated:
   - Must contain Chinese characters in `word_zh` and `example_zh`
   - Must contain English letters in `example_en`
   - Empty replies or non-Chinese/English characters are marked as invalid
3. Invalid batches are automatically retried (up to 3 times)
4. After max retries, the batch is skipped

### Rate Limiting

When the API rate limit is reached, the script:
- Saves a checkpoint file
- Stops execution
- To resume, run `translate.py` again

### Checkpoint

The script saves progress to `wordbank_checkpoint.json`. If the script stops for any reason (rate limit, error, etc.), simply run `translate.py` again to continue from where it left off.

## Output Format

```json
{
  "count": 8653,
  "words": [
    {
      "word": "about",
      "level": 0,
      "word_zh": "关于",
      "example_en": "This book is about history.",
      "example_zh": "这本书是关于历史的。",
      "index": "0"
    }
  ]
}
```

## CEFR Levels

| Level | Description |
|-------|-------------|
| 0 | A1 — Beginner |
| 1 | A2 — Elementary |
| 2 | B1 — Intermediate |
| 3 | B2 — Upper Intermediate |
| 4 | C1 — Advanced |
| 5 | C2 — Proficient |

## Files

- `translate.py` — Main translation script
- `wordbank_checkpoint.json` — Checkpoint file (auto-generated)
- `wordbank_final.js` — Final translated wordbank (generated when complete)
