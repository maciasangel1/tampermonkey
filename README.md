# MD Config Service

A CLI service that generates **Markdown configuration files** for AI model chats in [Open Web UI](https://github.com/open-webui/open-webui) based on interactive feedback questions.

## Overview

Running the service walks you through a series of questions about your desired AI model behaviour (name, purpose, tone, language, constraints, etc.).  
Once complete, it writes a structured `.md` file to the `output/` directory that you can use to quickly configure an AI chat in Open Web UI.

## Requirements

- Node.js ≥ 18

## Installation

```bash
npm install
```

## Usage

```bash
npm start
```

Or, if installed globally:

```bash
npm link
md-config
```

You will be asked the following questions:

| # | Question | Type |
|---|----------|------|
| 1 | Model name | Text |
| 2 | One-sentence description | Text |
| 3 | Primary use case | Choice |
| 4 | Tone | Choice |
| 5 | Primary language | Text |
| 6 | Expertise areas | Text (optional) |
| 7 | Constraints / topics to avoid | Text (optional) |
| 8 | Ask clarifying questions? | Yes / No |
| 9 | Preferred response format | Choice |
| 10 | Additional instructions | Text (optional) |

After answering all questions, the file is saved to:

```
output/<model-name>.md
```

## Output File Structure

Each generated `.md` file contains:

- **System Prompt** — paste directly into Open Web UI's system prompt field.
- **Configuration table** — tone, language, response format, etc.
- **Expertise Areas** — bullet list of topics the model knows well.
- **Constraints** — bullet list of topics the model should avoid.
- **Behaviour Guidelines** — auto-generated rules based on your answers.
- **Open Web UI Import Instructions** — step-by-step guide to import the config.

## Importing into Open Web UI

1. Open **Open Web UI** in your browser.
2. Navigate to **Settings → Models** (or **Workspace → Models**).
3. Click **"New Model"**.
4. Copy the **System Prompt** section from the generated `.md` file and paste it into the **System Prompt** field.
5. Fill in any other fields (name, description) from the **Configuration** table.
6. Save.

## Running Tests

```bash
npm test
```

## Project Structure

```
.
├── index.js            # CLI entry point
├── src/
│   ├── questions.js    # Feedback question definitions
│   ├── prompt.js       # Interactive CLI questionnaire
│   ├── generator.js    # Markdown generator and file writer
│   └── __tests__/
│       ├── generator.test.js
│       └── questions.test.js
└── output/             # Generated .md files (git-ignored)
```
