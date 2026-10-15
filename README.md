# AI Closet

AI Closet is a local web application for organizing clothing with the help of a vision-language model. Users can describe a garment, upload a photo, review the suggested details, and save it to a wardrobe. A searchable fashion dataset provides ready-made examples for demonstrations and experiments.

The application runs its AI models on the host computer and stores clothing records in SQLite databases. It is a research prototype for exploring multimodal clothing cataloging and comparing local models.

## Features

- **Clothing analysis:** Generate clothing attributes from text, a photo, or both. Review and edit the result before saving.
- **Personal wardrobe:** Browse saved garments and update their details.
- **Clothing library:** Search product images by name, category, type, color, and gender. Add individual products to the wardrobe or use their photos for AI analysis.
- **Starter collection:** Add 30 men's clothing items in varied styles and colors. Repeated additions skip duplicates.
- **Demo selections:** Create separate 20-, 50-, or 100-item selections from the library. Creating a new demo replaces the previous demo selection.
- **Model comparison:** Ask the same text question with two local models and view their answers and request times.
- **Optional remote access:** Open the website from another device through a private Tailscale connection.

## Models

| Model | Precision | Purpose |
| --- | --- | --- |
| Qwen3-VL-2B-Instruct-FP8 | FP8 | Smaller model for text and image requests |
| Qwen3-VL-4B-Instruct-FP8 | FP8 | Larger model for comparison |

Models are served using vLLM. Only one model runs at a time; switching releases the current model before loading the next. The first use may download model files from Hugging Face.

## Requirements

The current setup has been tested on Ubuntu with Python 3.12, an NVIDIA RTX 4060 with 8 GB of VRAM, and 16 GB of system RAM. These describe the tested environment, not guaranteed minimum requirements for every configuration.

The Python environment must contain vLLM, a compatible CUDA-enabled PyTorch installation, FastAPI, Uvicorn, the OpenAI Python client, and Pillow. The OpenAI client communicates with the local vLLM server; this application does not require an OpenAI API key or paid cloud inference.

Internet access is needed for initial software, model, and dataset downloads. Available disk space must accommodate the model files and optional clothing library. GPU memory settings may need adjustment on other hardware.

## Installation

Clone the repository on the Linux computer that will run inference:

```bash
git clone https://github.com/YOUR_USERNAME/ai-closet.git
cd ai-closet
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Replace `YOUR_USERNAME` with the repository owner. A private repository requires GitHub authentication. The pinned dependencies reflect the tested development environment; a different GPU or CUDA setup may require compatible package versions. Installation and model downloads can take time and several gigabytes of disk space.

The repository includes application code and one sample image. It does **not** include populated databases, downloaded models, logs, backups, or private network configuration. A fresh checkout starts with an empty wardrobe. Import the optional dataset using the instructions below, then use the starter collection or add clothing manually.

## Run the application

From the project directory, activate the environment and start the server:

```bash
source .venv/bin/activate
```

Then run:

```bash
python web/app.py
```

Open [http://127.0.0.1:7860](http://127.0.0.1:7860) in a browser.

The included `start_gui.sh` can be used instead. It selects an activated environment, the project `.venv`, or an existing `~/venvs/vllm` environment. Set `AI_CLOSET_PYTHON` to choose an explicit interpreter:

```bash
bash start_gui.sh
```

Keep the server terminal open. Press **Ctrl+C** in that terminal to stop the website and any model it started. Closing the browser alone does not stop the server.

### Analyze and save clothing

1. Select a model and click **Load selected model**. Wait until the AI is ready.
2. Open **Add clothing** and enter a description, choose a photo, or provide both.
3. Click **Analyze clothing**.
4. Check the suggested category, type, color, and formality. Add season or brand information if known.
5. Click **Save to wardrobe**.

AI suggestions can be incorrect. Unknown values can remain empty, and saved details can be edited later.

### Use the clothing library

Open **Clothing library** to search the dataset. The initial gender filter is **Men**, and the filters can be changed.

- **Add to My wardrobe** saves a product using its dataset labels, without requiring AI inference.
- **Try with AI** opens the product photo in the analysis form. Click **Analyze clothing** to generate a prediction; the dataset labels are not supplied to the model.
- **Build demo wardrobe** creates a separate sample selection for browsing. It does not automatically add that selection to My wardrobe.

Imported wardrobe entries are marked as library items. Their original dataset labels are preserved separately from editable attributes and AI predictions.

## Import the dataset

The library uses [Fashion Product Images (Small), by Param Aggarwal](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small). Download the dataset ZIP and run the following from the project directory, replacing the example path with the downloaded file:

```bash
python scripts/import_fashion.py /path/to/fashion-product-images-small.zip
```

The importer creates `data/fashion.sqlite3`, reports missing images, and replaces any existing library database. It does not modify the personal wardrobe database. The current imported dataset contains 44,441 products with images.

These are small preview images with source-provided labels. They are useful for browsing and demonstrations, but independent, higher-quality images are preferable for final model evaluation. Consult the dataset page for its terms and attribution information.

## Project structure

```text
ai-closet/
├── web/
│   ├── index.html          # Page layout, styling, and browser interactions
│   ├── app.py              # Web server, AI requests, and wardrobe operations
│   ├── model_runtime.py    # Model loading, switching, and GPU settings
│   ├── library.py          # Dataset search and demo selections
│   ├── wardrobe_import.py  # Library imports and starter clothing selection
│   ├── test_app.py         # Application and model lifecycle checks
│   └── test_library.py     # Dataset import and browsing checks
├── scripts/
│   ├── catalog.py          # Terminal cataloging and attribute validation
│   ├── test_catalog.py     # Manual image inference script
│   ├── import_fashion.py   # Dataset ZIP importer
│   └── setup_remote.py     # Private Tailscale access setup
├── data/                   # Databases, sample images, and local configuration
├── logs/                   # Model startup and error logs
├── backups/                # Saved copies from previous changes
├── start_gui.sh            # Optional launch script
├── startup.log             # Earlier standalone model startup log
├── README.md               # Project documentation
├── GUI_README.md           # Link to the main documentation
├── requirements.txt        # Tested runtime dependencies
├── requirements-dev.txt    # Additional test dependency
├── .gitignore              # Files excluded from version control
└── REMOTE_ACCESS.md        # Additional remote-access notes
```

### Stored data

| Location | Contents |
| --- | --- |
| `data/wardrobe.sqlite3` | Saved garments, photos, edited attributes, source labels, and AI prediction records |
| `data/fashion.sqlite3` | Searchable product library and images |
| `data/demo.sqlite3` | Product IDs in the current demo selection |
| `data/images/` | Sample image files |
| `data/remote-host.txt` | Optional approved Tailscale hostname |

Model files are downloaded to the Hugging Face cache, normally outside the project directory. Back up the wardrobe database before making database changes.

## Access from another device

For private remote access, install Tailscale on the host and viewing devices and sign in to the same private network. With Tailscale connected, run this on the host:

```bash
python scripts/setup_remote.py
```

Follow any administrator or HTTPS setup prompts, then restart AI Closet. Open the private HTTPS address printed by the script on the other device.

The host must remain awake, online, and running the application. Reconnecting normally uses the same private address. The website and inference server remain bound to local ports 7860 and 8000; Tailscale Serve provides access to the website within the private network.

## Development

Common changes belong in these files:

- **Appearance and buttons:** `web/index.html`
- **AI prompts and application behavior:** `web/app.py`
- **Model choices and GPU settings:** `web/model_runtime.py`
- **Library search:** `web/library.py`
- **Starter selection and imported attributes:** `web/wardrobe_import.py`

Refresh the browser after editing the HTML file. Restart the server after changing Python code. Changes to the model menu may require updates in both `model_runtime.py` and `index.html`.

Run the automated checks from the project directory with the project environment active:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s web -p 'test_*.py' -v
```

The automated checks use temporary databases and mocked AI responses; they do not establish real model quality or GPU compatibility.

## Current limitations

- **Ask AI is a standalone text experiment.** It does not read the wardrobe database or retain a conversation across questions.
- Outfit recommendations grounded in saved garments and automatic model routing are not implemented yet.
- Comparison results remain in the browser only until refresh or a different question is submitted.
- Displayed request times exclude model loading. The model configurations have different GPU memory budgets, so these timings are not a controlled benchmark.
- The application is intended for local use or a trusted private network. It does not provide separate user accounts or a production hosting setup.

## Troubleshooting

- **The website does not open:** Start the server and check the terminal for errors.
- **The AI is offline:** Load a model from the sidebar and wait for it to become ready.
- **A model fails to load:** Check the startup details in the website or the corresponding file in `logs/`. Confirm that CUDA is available and sufficient GPU memory is free.
- **An action asks for a refresh:** Reload the page after restarting the server.
- **The clothing library is unavailable:** Import the dataset using the command above.
- **Remote access fails:** Check that both devices are connected to Tailscale and that the host is awake with the website running.


## Save changes to GitHub

Git does not upload edits automatically. After making and checking a change, run:

```bash
git status
git diff
git add .
git diff --cached
git commit -m "Describe the change"
git push
```

Review the staged changes before committing. The `.gitignore` keeps local databases, model files, logs, backups, and environment files out of commits. To retrieve newer commits from another computer when the working directory is clean, run `git pull --ff-only` before starting work.

GitHub stores the source code; pushing a commit does not deploy the application or start its GPU server. Wardrobe/database backups must be managed separately from code history.

## Sample image attribution

The bundled white T-shirt sample is from [Mockupbee on Pexels](https://www.pexels.com/photo/white-t-shirt-on-white-surface-12039633/). The sample image and optional fashion dataset retain their respective source terms.
