# Legal Research Powerhouse

An add-on for Claude Code that makes Claude research law the way a careful associate does: it finds the authority, reads it, saves a copy, and keeps a record of every source before it writes a word that cites it.

Claude will not cite a case or statute it has not pulled from a real legal database in your session. If it tries, the add-on blocks the draft until the authority is found, read, and recorded.

> This is a research tool for lawyers and law students. It does not give legal advice, and it does not replace KeyCite or Shepard's. You remain responsible for every citation you file.

## What you get

- **Case law from CourtListener**, the free legal database run by the Free Law Project. Claude searches, reads the full opinion, and saves it.
- **Statutes and regulations.** The full Official Code of Georgia and the Georgia Constitution (through Georgia Commons), plus the U.S. Code, the Code of Federal Regulations, the Federal Register, Congress.gov, and Regulations.gov.
- **A source ledger for every matter.** Each authority gets an entry with where it came from, when, a fingerprint of the saved text, and whether it has been checked.
- **A citation gate.** Claude cannot save a draft that cites an authority missing from the ledger.
- **Good-law screening.** A free first-pass check for negative treatment, labeled honestly as a screen. A KeyCite checklist tells you exactly what to confirm by hand in Westlaw.
- **Bluebook and Georgia citation formatting**, quotation checks against the saved text, and a cite-check report you can open in your browser.
- **A workbench inside Claude Code**: a Home screen, a matter picker, panes for your authorities, sources, and drafts, and a status band that shows what still needs your attention.

Claude never logs in to Westlaw, Lexis+, or Bloomberg Law; their terms forbid automation. When a paywalled treatise or Restatement would help, Claude writes you the exact searches to run, and you report back what you found.

## Before you start

You need four things. All are free except the Claude subscription.

1. **A Claude plan that includes Claude Code** (Pro or Max). Install the Claude desktop app from [claude.ai/download](https://claude.ai/download) and use its **Code** tab, or install Claude Code in a terminal. You need Claude Code version 2.1.287 or later.
2. **Git**, to download this project. Windows: [git-scm.com/download/win](https://git-scm.com/download/win). Mac: run `git --version` in Terminal and accept the install prompt.
3. **uv**, which runs the add-on's Python tools. Follow the one-line install at [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/). uv installs the right Python for you.
4. **A free CourtListener account** at [courtlistener.com](https://www.courtlistener.com/register/).

## Set it up yourself (about 15 minutes)

You type the commands below into a terminal: **PowerShell** on Windows, **Terminal** on a Mac. Paste one line at a time and press Enter.

**Step 1. Download the project** into a folder you will keep, for example your Documents folder.

```
cd ~/Documents
git clone https://github.com/GlebSoftware/legal-research-powerhouse.git
cd legal-research-powerhouse
```

**Step 2. Install the add-on into Claude Code.** Run these from inside the `legal-research-powerhouse` folder.

Windows (PowerShell):

```powershell
claude plugin marketplace add "$PWD"
```

Mac:

```
claude plugin marketplace add "$(pwd)"
```

Then, on either system:

```
claude plugin install legal-research@alr
claude plugin install legal-workbench@alr
```

If your terminal says `claude` is not found, open the Claude desktop app once, or install the Claude Code command line tool, and try again.

**Step 3. Connect CourtListener.** On [claude.ai](https://claude.ai), open **Settings**, then **Connectors**. Add CourtListener; if it is missing from the list, choose **Add custom connector** and enter `https://mcp.courtlistener.com/`. Sign in with your CourtListener account when asked. Claude Code picks the connector up automatically.

A free CourtListener account allows 125 requests a day. Students with a `.edu` email address can request CourtListener's free EDU membership, which raises the limit to 1,000 an hour.

**Step 4 (optional). Add free federal API keys.** These unlock GovInfo, Regulations.gov, and Congress.gov. Copy the example settings file:

```
cp .env.example .env
```

Open `.env` in any text editor and paste in your keys. Each line in the file says where to sign up. The `.env` file stays on your computer and is never uploaded.

**Step 5. Open the folder in Claude Code.** In the desktop app's Code tab, choose the `legal-research-powerhouse` folder. In a terminal, run `claude` from inside it. Always work from this folder: the add-on keeps your matters here.

**Step 6. Start your first matter.** Type:

```
/research torts/negligence-memo Is a social host liable in Georgia for injuries caused by an intoxicated adult guest?
```

Claude asks for anything missing (jurisdiction, audience, whether the assignment is a closed universe), writes a research plan, and waits for your go-ahead before it searches. You can also use the **New matter** form on the Home screen.

## Have Claude set it up for you

Open Claude Code in any folder and paste the prompt below. Claude does the installing and stops to ask you for the steps only you can do, such as connecting CourtListener and entering API keys.

```text
Install the Legal Research Powerhouse add-on for Claude Code from
https://github.com/GlebSoftware/legal-research-powerhouse and get it working on this computer.

1. Check that git, uv, and Claude Code 2.1.287 or later are installed. If one is missing,
   tell me what to install and give me the official download link. Do not install
   system software without asking me first.
2. Clone the repository into my Documents folder (ask me if I want a different place).
3. From inside the cloned folder, run:
   claude plugin marketplace add "<absolute path to the cloned folder>"
   claude plugin install legal-research@alr
   claude plugin install legal-workbench@alr
4. Run `uv run pytest -q` in the cloned folder and tell me whether the tests pass.
5. Copy .env.example to .env. Ask me whether I want to add the optional federal API keys.
   If I do, tell me where to sign up for each one and let me paste the keys into .env
   myself. Never print, repeat, or commit a key.
6. Tell me to connect CourtListener at claude.ai > Settings > Connectors (as a custom
   connector at https://mcp.courtlistener.com/ if it is not listed). You cannot do that
   step for me.
7. Tell me to reopen Claude Code in the cloned folder and type /research to start a matter.

Never commit or upload anything from the research/ folder or the .env file.
```

## Everyday use

| You want to | Type |
|---|---|
| Start a new research matter | `/research <course>/<assignment> <question>` |
| Find and read a case | `/find-case Palsgraf v. Long Island R.R.` |
| Pull a statute or regulation | `/find-statute O.C.G.A. § 51-1-40` |
| Check whether a case is still good law (free screen) | `/validate <case>` |
| Format a citation | `/bluebook <case or statute>` |
| See every authority in the matter | `/ledger show` |
| Record your own KeyCite result | `/ledger mark <id> keycite=<result>` |
| Get Westlaw searches for a treatise or Restatement | `/secondary request <issue>` |
| Audit a draft's citations and quotations | `/cite-check` |

Or just ask a legal question in plain English. The add-on routes it to the right research steps.

Your work lives in `research/<course>/<assignment>/`: the question, the plan, the ledger (`authorities.json`), the saved sources, your notes, your drafts, and the audit reports.

## Coverage

- **Case law:** every jurisdiction CourtListener covers, federal and state.
- **Statutes:** Georgia and federal. Other states' statutes are on the roadmap; for now, cite them only after you retrieve them yourself.
- **Jurisdiction default:** Federal. Name any state when you start a matter.

## Your privacy

- Everything you research stays in your copy of this folder. The `.gitignore` file keeps your `research/` folder, your `.env` keys, and your personal Claude settings out of git, so they never reach GitHub even if you publish your own copy.
- Searches go to CourtListener, Georgia Commons, and the federal government APIs. Do not type client-identifying details into a research question. Describe the facts generically.
- Claude itself runs under your Anthropic account and its terms. Check your firm's policy before using any AI tool on client work.

## Troubleshooting

- **"CourtListener is disconnected."** Reconnect the CourtListener connector at claude.ai > Settings > Connectors, then restart Claude Code.
- **The workbench panes do not appear.** Update Claude Code to 2.1.287 or later. If your organization manages your Claude Code settings, an administrator must allow the `legal-workbench` add-on.
- **A federal tool says an API key is missing.** Add the key to `.env` (Step 4) and restart Claude Code.
- **Updating to a new version:** run `git pull` in the folder, then `claude plugin marketplace update alr`, `claude plugin update legal-research@alr`, and `claude plugin update legal-workbench@alr`, and restart Claude Code.

## Roadmap

- **Personal information protection.** Detect client names, Social Security numbers, birth dates, medical details, and other sensitive facts before a question leaves your computer, and redact them from search queries and drafts.
- **A better free KeyCite substitute.** Read every citing opinion's treatment of a case through CourtListener's citation network and classify it (followed, distinguished, questioned, overruled), so the manual KeyCite list shrinks to the cases that truly need it.
- **An open-source case-law model.** Find or train an open neural model over the CourtListener corpus for meaning-based case search and treatment classification that runs without a paid database.
- **More states' statutes** beyond Georgia and federal law.
- **One-step installation** for people who never open a terminal.

## For developers

```
claude --plugin-dir plugins/legal-research --plugin-dir mods/legal-workbench
uv run pytest -q
claude plugin validate mods/legal-workbench
claude plugin test mods/legal-workbench
```

| Folder | Contents |
|---|---|
| `plugins/legal-research/` | The plugin: skills, slash commands, agents, hooks, and the Python scripts behind the ledger, citation gate, formatter, and audits |
| `mods/legal-workbench/` | The Claude Code mod: Home screen, panes, status band, and the citation gate on tool calls |
| `servers/uslaw-mcp/` | MCP server for federal statutes, regulations, and government sources |
| `scripts/` | Utilities for local data mirrors and skill validation |
| `data/conan/` | Tables from the Constitution Annotated (overruled decisions, laws held unconstitutional) |

## Licenses and credits

Created by Gleb Alikhver.

- The `citation-format`, `research-protocol`, and `validity-check` skills adapt work by DingDuff Inc. under the DingDuff Skills License 1.0, which permits noncommercial use only. These versions are modified; they are not official and not endorsed by DingDuff Inc. See the `LICENSE.md` file in each skill folder.
- CourtListener data and the eyecite, reporters-db, and courts-db libraries come from the Free Law Project (BSD-2).
- Georgia Commons code text is CC0. Federal government works are in the public domain.
