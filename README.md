<img src="assets/fn_logo.jpeg" alt="Finite News Logo">
  
🗞️ Extra extra! This is Finite News: the mindful, personalized newspaper.   
  
## 🤔 Motivation
I happily pay for subscriptions to quality news sources and support essential journalism! But increasingly news websites and newsletters are filled with clickbait, pop-ups, and attention vampires.
  
I made Finite News to deliver a lean, personalized daily news email. Its goal is to reduce distractions and focus on what's happening in the world.
  
## 👀 Features
Finite News can...
 - Give you the day's headlines from your trusted APIs, feeds, and websites.
     - Enforce strict limits on the volume of news
     - Leave out ads and links.
     - Applies rules and large language models (LLMs) to remove opinions and clickbait, consolidate related headlines, and only show news you haven't seen before.
 - Forecast your local weather.
 - Get you the latest XKCD comic and James Webb photo.
 - Tell you when your favorite team plays tonight and last night's scoreboard.
 - Deliver custom alerts, like when your train station has a major delay.
 - List upcoming events of interest to you.
  
## 📰 Make your own newspaper
### How it works
Finite News is Python code that's set up as a Google Cloud Run job. It could be run locally as a cron job or deployed on other platforms, too.
  
### Concepts
- **Publication:** The general processes that are shared by every issue and subscription.
- **Subscription:** The customizations that personalize Finite News for a single person (subscriber).
- **Issue:** One email delivered to one subscriber.
  
### Getting set up
1. Set up the local code environment on your computer or server. This is where you'll work on the newspaper and deploy it to the cloud.
    1. Clone this repo as a directory locally.
    2. [Install uv](https://docs.astral.sh/uv/getting-started/installation/) on your computer.
    3. Run `uv sync` to create the virtual environment.
    4. Run `uv run pre-commit install`
2. Configure your newspaper (see "Designing your newspaper" section).
3. Set up a Google Cloud account. 
    - You can follow the general setup steps for a Google Cloud job, like the early parts of this [quickstart](https://cloud.google.com/run/docs/quickstarts/jobs/build-create-python).
    - Create a new Google Cloud project for Finite News.
    - Install the [gcloud command line utility](https://cloud.google.com/sdk/docs/install) on your computer.
4. Make a new Google Cloud bucket. Add the files you created in "Designing your newspaper"
5. Create an account on `sendgrid.com`. This lets you send the emails (via an API).
6. Store your secrets. 
    - You'll need the following secrets:
        - `SENDGRID_API_KEY`
        - `FN_BUCKET_NAME`
        - (Optional) `OPENAI_API_KEY` if you optional add GPT to filter headlines (see below).
        - Any API keys you signed up for custom news sources
    - Store each secret in two places:
        1. In Google Cloud Secrets Manager. Once deployed as a Cloud Run Job, we'll expose these secrets as environment variables.
        2. As local environment variables on your computer (e.g. in .zshrc, `export SECRET_NAME="secret_value"`)
7. (Optional) Download a free language model to enable the Smart Deduper. 
    - The Smart Deduper removes headlines that are similar to others in the same issue. It uses a language model to measure the similarity (in meaning) of headlines. 
    - I like to use the model [`paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2). It works in multiple languages.
        - But you can use another model supported by https://huggingface.co/sentence-transformers
    - Download the language model to the project folder. Here's one way:
        1. Run the following block of code in this project's virtual environment. You can plop it in a cell in the Jupyter notebook `dev.ipynb`.
            ```python
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            ```
        2. That will download all the model files to a central location on your computer: `~/.cache/hub/sentence-transformers/{MODEL}`. Example: `~/.cache/hub/sentence-transformers/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2`
        3. Move that `{MODEL}` subdirectory into the root Finite News project folder, under `models/smart-deduper/{MODEL}`
    - In `publication_config.yml` specify the path to the model in the Finite News project folder, **specifically the `snapshots/{HASH}`** folder inside it. 
        - Example: `path_to_model: "models/smart-deduper/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/8d6b950845285729817bf8e1af1861502c2fed0c"`
8. (Optional) Create an API account on [openai.com](www.openai.com), to use GPT to remove low-quality headlines (clickbait etc).
    - 💁‍♂️ Tip: I find that using manual rules, configuring `substance_rules.yml` in your newspaper files, does more to improve the quality of headlines than the GPT feature. It takes trial and error to find the keywords to exclude the junk. 
    - Note: Using the OpenAI API will incur charges to your OpenAI account.
    - If you do this, add the secret `OPENAI_API_KEY` to the secrets you created above.
    - And update the code calls to `run_finite_news()` (in `run.py` and `dev.ipynb`) by adding the argument `disable_gpt=False`.
9. Test locally using the notebook `dev.ipynb`.
    - Select the virtual environment `.venv` in the project folder (created when you did `uv sync`). 
    - To run Python scripts directly from your local environment, you can simply use `uv run run.py`.
10. Deploy.
    - If you use a local cron job, you can schedule the command in this project directory and run as `uv run run.py`.
    - To run it in the cloud as a Google Cloud Run job:
        - Follow the general steps of this [quickstart](https://cloud.google.com/run/docs/quickstarts/jobs/build-create-python). 
        - Enable Google Cloud Run and configure your computer to operate it with the `gcloud` command line utility. 
        - Ensure the Cloud Run job has permissions to access the secrets and Cloud Storage bucket in your project.
        - Deploy the code from your computer to a new Cloud Run job. 
            - You can use the bash script `./deploy-finite-news.sh`. Update as necessary for your region etc. 
            - This script will build a container out of your code, upload it to the Google Cloud's Artifact Registry, and create a Cloud Run job.
            - The script will tell you when it's done.
        - You can run the job! Either
            - Execute the new job as a one-off using the [Google Cloud Console](https://console.cloud.google.com/run/jobs) or gcloud command line.
            - Or create a [Scheduler Trigger](https://console.cloud.google.com/run/jobs) to run the job on a schedule, such as once a day.
### Changing your newspaper
* **To updating the configuration** (such as adding a new subscriber config file or changing the `publication_config.yml`): Upload the changed/new files to your existing Google Cloud Storage bucket.
* **To update the code:**
    1. To add, remove, or update dependencies, use [`uv` commands](https://docs.astral.sh/uv). 
        - If you haven't used `uv` before, it's awesome. Use its commands like you would use `pip` or `conda`. 
    2. To deply new code to the Google Cloud job:
        1. Commit code changes to your local git repo.
            - When you commit, a `uv` pre-commit will update the `requirements.txt` file if any dependencies have changed. 
        2. Run `./deploy-finite-news.sh` to deploy the new code. 
            - This will build a new version of the container, upload it to the Google Cloud's Artifact Registry, and point the existing Cloud Run job to the new version of the container.
            - The deployment will use the `.python-version` and `requirements.txt` files to install the right version of Python and the dependencies in the container.
        3. If you set up a Scheduler Trigger to run the job on a schedule, no changes should be needed! 
            - The job should automatically point to the new version of the container.
        4. You may want to delete the old version of the container in the Artifact Registry, if you don't need it. 
            - Cuz they charge you keeping containers up there, like a storage unit.
  
### Designing your newspaper
🚨🚨 Comply with the Terms of Service of your sources and APIs.  
  
Create the following files. See the `samples_files` folder for examples. Later, your files will go in your Google Cloud Storage Bucket.
- `publication_config.yml`: General choices for how to run Finite News
    - This includes setting up individual news sources. See the sample `publication_config.yml` for instructions.
    - If you need an API key to access a particular news source, add `api_key_name: {NAME OF YOUR API KEY}` under that source in `publication_config.yml`. Then add a new secret/environment variable for `{NAME OF YOUR API KEY}` as described above in Set Up for the other secrets.
    - To disable GPT, delete the `gpt` section in `publication_config.yml`.
- `config_*.yml`: Configuration for each subscription (each daily email). 
    - To add a new subscriber, create a new `config_their_name.yml` file and upload to the bucket. 
    - Finite News creates the list of subscribers by looking for all YML files in the bucket that begin with `config_`.
- `template.htm`: The layout for the email. The parts in `[[ ]]` are populated by the code at runtime.
- `substance_rules.yml`: Policies for identifying "low substance" headlines to always drop. You can add rules to remove headlines on topics you don't want to hear about or recurring noise. 
- `thoughts_of_the_day.yml`: (optional) Shared list of jokes and quotes sampled for Thought of the Day. To enable, in `config_*.yml` file(s) set `add_shared_thoughts=True`.
  
## ❤️ Bugs, questions, and contributions
You're awesome, thank you! The best way is to create a new Issue.