<img src="assets/fn_logo.jpeg" alt="Finite News Logo">
  
🗞️ Extra extra! This is Finite News: the mindful, AI-assisted newspaper.   
  
## 🤔 Motivation
I happily pay for subscriptions to quality news sources and support essential journalism! But increasingly news websites and newsletters are filled with clickbait, pop-ups, and attention vampires.
  
I made Finite News to deliver a lean, personalized daily news email. Its goal is to reduce distractions and focus on what's happening in the world.
  
## 👀 Features
Finite News can...
 - Give you the day's headlines from your trusted APIs, feeds, and websites.
     - Enforcing strict limits on the volume of news, and leaves out ads and links.
     - Applies multiple large language model (LLMs) and rules to consolidate headlines that are about the same topic, remove opinions and clickbait, and only show news you haven't seen before.
 - Forecast your local weather.
 - Get you the latest XKCD comic.
 - Alert you if your favorite NBA or NHL team plays tonight.
 - List upcoming events of interest to you.
 - Tell you if a new electric car is eligible for the $7500 tax rebate in the US.
 - Tell a joke.
  
## 📰 Make your own newspaper
### How it works
Finite News is set up to run as a scheduled Google Cloud Run job.
  
### Concepts to know
- **Publication:** The general processes that are shared by every issue and subscription.
- **Subscription:** The customizations that personalize Finite News for a single person (subscriber).
- **Issue:** One email delivered to one subscriber.
  
### Set up
1. First, you need to create data files that configure everything about Finite News. See "Designing your newspaper" below.
2. Create a Google Cloud account.
3. Clone this repo as a directory locally.
4. Set up secrets. We'll put them in two places:
    - As local environment variables (e.g. in .zshrc, `export SECRET_NAME="secret_value"`)
    - In Google Cloud Secrets Manager. Once deployed as a Cloud Run Job, we'll expose these secrets as environment variables.
5. Make a new Google Cloud bucket. Add the files you created in "Designing your newspaper"
    - Add a secret & local environment variable called `FN_BUCKET_NAME` with the name of the bucket on Google Cloud Storage.
6. Create an account on `sendgrid.com`. This lets you send emails in the notebook (via an API).
    - Add a secret/local environment variable for `SENDGRID_API_KEY`
7. (Optional) Download a language model to use for the Smart Deduper.
    - Choose a model supported by https://huggingface.co/sentence-transformers
        - For default, including multilingual support, consider paraphrase-multilingual-MiniLM-L12-v2
    - Download the model. One way is to run this in a cell of `dev.ipynb`. Replace with your model name, if you change it.
        ```python
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        ```
        - That downloads the model files to `~/.cache/hub/sentence-transformers/`. For this example model, the subdirectory would be `models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2`
    - Copy the model subdirectory to the project folder under `models/smart-deduper/`
    - In `publication_config.yml` specify the path to the model in the project folder, specifically the `snapshots/hash`. 
        - Example: `path_to_model: "models/smart-deduper/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/8d6b950845285729817bf8e1af1861502c2fed0c"`
8. (Optional) Create an API account on openai.com, to use GPT to use as a Substance Filter, to remove low-quality headlines
    - Add a secret/local environment variable for `OPENAI_API_KEY`
9. Test locally using the notebook `dev.ipynb`.
11. Deploy.
  
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
You're awesome, thank you! The best way is to create a new Issue or Pull Request.