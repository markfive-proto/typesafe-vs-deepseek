# Context window management at runtime

Server-side truncation or rejection logic for requests that exceed a model's context limit, plus the accounting that determines how much of the window is actually usable once system prompts and reserved output space are subtracted.
