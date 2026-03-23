# Anthropic API Setup for Pipeline LLM Reports

## 1. Get an API Key

1. Go to https://console.anthropic.com and sign in or create a personal account
2. Navigate to **Settings** > **API Keys**
3. Click **Create Key**, name it `thesis-pipeline`, copy the key (starts with `sk-ant-`)

## 2. Add Key to GitHub Repository Secrets

1. Go to https://github.com/VirginiaTechWLee/Thesis_Workflow/settings/secrets/actions
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: paste your key (starts with `sk-ant-`)
5. Click **Add secret**

## 3. Verify It Works

If the Nastran Utility Workflow (`nastran_utility.yml`) has already run successfully with a simulation report, the same key works for the super workflow LLM reports. No additional configuration needed.

## Usage

### Nastran Utility Workflow (Task 1)
- Generates 1 report per run (`simulation_report.md`)
- Triggered separately from the super workflow

### Super Workflow LLM Reports (Task 2)
- Generates 7 reports per run when `llm_reports=true`
- Enable via GitHub Actions UI (checkbox) or set `pipeline.llm_reports: true` in `fem_input/config.yaml`
- Reports are written to `D:\thesis_database\pipeline_reports\<study>_<timestamp>\`

### Reports Generated
| # | Report | When | What It Reads |
|---|--------|------|---------------|
| 1 | Pre-Run FEM Health Check | After validation | DAT file |
| 2 | Study Plan Summary | After HEEDS project generation | config.yaml + .heeds file |
| 3 | HEEDS Run Status | After HEEDS completes | Study log + design verification |
| 4 | Database Health | After DB import | SQLite tables |
| 5 | Feature Matrix | After feature extraction | training_matrix.npz |
| 6 | Classification | After classifier training | classification_report.txt |
| 7 | Executive Summary | End of pipeline | All 6 prior reports |

## Cost

- Each API call uses Claude Sonnet (~$0.01-0.02 per report)
- 7 reports per full pipeline run = ~$0.10-0.15 per run
- The Nastran Utility Workflow adds ~$0.01-0.02 per run
- Monthly cost depends on run frequency — at 5 runs/week, expect ~$2-3/month
