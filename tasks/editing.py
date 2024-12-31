"""🪥 Editing: Functions to clean up reporting results"""

import emoji
from google.cloud import storage
import logging
import openai
import os
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
from time import sleep

from tasks.io import get_fn_secret, load_file_from_bucket


def remove_emojis(text):
    """Utility function that removes all emojis from a string
    ARGUMENTS
    text (str): A string

    RETURNS
    text without emojis (or new whitespace created by removing emojis)

    """
    return emoji.replace_emoji(text, replace="").strip()


def cache_issue_content(content, cache_path):
    """Export a list of this issue's headlines and other content that we don't want to show again in the next issue.

    NOTE: Must call this before edit_research so we carry forward repeats that were dropped too

    ARGUMENTS
    content (list of str): Headlines or other content items that shouldn't be repeated in subsequent issues
    bucket_name (str): The name oof the bucket on Google cloud storage where required files are stored.
    cache_path (str): The path on the bucket for this subscriber's cache of last issue's headlines

    RETURNS
    None
    """
    bucket_name = get_fn_secret("FN_BUCKET_NAME")
    with storage.Client().bucket(bucket_name).blob(cache_path).open("w") as cache_file:
        for item in content:
            cache_file.write(f"{item}\n")
        logging.info(f"Wrote issue content to {bucket_name+cache_path}")


def apply_one_headline_keyword_filter(headlines, keyword):
    """Limit the issue to a maximum of one headline that mentions this keyword.

    ARGUMENTS
    headlines (list of str): Headlines from all sources

    RETURNS
    List of headlines except those that contain this keyword
    """

    new_headlines = []
    kw_counter = 0
    keyword = keyword.lower()
    for headline in headlines:
        # TODO: Could add spaCy tokenizer, split on spaces, punctuation. But the benefit would be teeny. Empirically this has been working perfectly for months.
        has_kw = keyword in headline.lower()
        kw_counter += has_kw
        if not has_kw or kw_counter <= 1:
            new_headlines.append(headline)
    return new_headlines


def remove_items_in_last_issue(new_items, cache_path):
    """Delete content that we already presented in the last issue.

    Ignores emojis in the comparison. That way a preface emoji (could be changed in publication_config) alone
    wouldn't prevent a match with an identical headline in the cache (with the old preface)

    TODO: Ignore the entire preface in this comparison. Even better, don't add the preface till after editing headlines.

    ARGUMENTS
    new_items (list of str): Fresh content
    cache_path (str): The path on the Google Cloud Storage bucket for this subscriber's cache of the last issue's content

    RETURNS
    List of content from new_items that was not in the last issue
    """
    last_issue_items = [
        remove_emojis(line) for line in load_file_from_bucket(cache_path)
    ]
    fresh_items = [
        item for item in new_items if remove_emojis(item) not in last_issue_items
    ]
    logging.info(
        f"Removed items that were in last issue: {[item for item in new_items if item in last_issue_items]}"
    )
    return fresh_items


def unnest_list(l_of_ls):
    """Extract headlines from all sources we researched.

    ARGUMENTS
    l_of_ls (list of lists)

    RETURNS
    Flat list of string headlines retrieved from all sources
    """
    # Remove sublists that are None
    l_of_ls_rinsed = [li for li in l_of_ls if li]
    return [item for sublist in l_of_ls_rinsed for item in sublist]


def lower_list(li):
    """Helper function to lowercase the items in a list of strings.

    ARGUMENTS
    li (list of str): A list of headlines

    RETURNS
    List of lowercase headlines
    """

    if not li:
        return None
    return [item.lower() for item in li]


def breaks_rule(headline, cant_begin_with, cant_contain, cant_end_with):
    """Evaluate whether a headline breaks any of the passed sets of editorial rules

    ARGUMENTS
    headline (str): The text to evaluate
    cant_begin_with (list of str): Text that a headline cannot start with
    cant_contain (list of str): Text that cannot exist anywhere in a headline
    cant_end_with (list of str): Text that a headline cannot end with

    RETURNS
    True if this headline violates any rule
    """

    # Ignore emojis, which often preface the headline (and interfere with cant_begin_with
    # TODO: Edit headlines before adding prefaces
    headline_clean = remove_emojis(headline)

    for phrase in cant_begin_with:
        if headline_clean.startswith(phrase):
            return True
    for phrase in cant_contain:
        if phrase in headline_clean:
            return True
    for phrase in cant_end_with:
        if headline_clean.endswith(phrase):
            return True


def apply_substance_rules(headlines, substance_rules):
    """Remove headlines that fail our logic for ensuring a headline is substanative.

    ARGUMENTS
    headlines (list of str): The headlines retrieved from all sources
    substance_rules (dict): The editorial rules, which consist of lists of phrases

    RETURNS
    List of headlines that pass all substance rules

    """
    cant_begin_with = lower_list(substance_rules.get("cant_begin_with", []))
    cant_contain = lower_list(substance_rules.get("cant_contain", []))
    cant_end_with = lower_list(substance_rules.get("cant_end_with", []))
    removed_headlines = [
        headline
        for headline in headlines
        if breaks_rule(headline.lower(), cant_begin_with, cant_contain, cant_end_with)
    ]
    logging.info(f"Substance rules removed: {removed_headlines}")
    kept_headlines = [
        headline for headline in headlines if headline not in removed_headlines
    ]
    return kept_headlines


def smart_dedup(headlines, smart_dedup_config, prefaces_to_ignore=[]):
    """Use semantic de-duping to avoid showing two headlines about the same news events, even if they use different words.

    ARGUMENTS
    headlines (list of str): The headlines from research
    smart_dedup_config (dict): Publication's settings for using the smart deduplication
    prefaces_to_ignore (list): A list of repeated prefaces that may appear at beginnings of headlines, if we want smart_dedup to ignore them when computing headline similarity.
                               So we don't get high similarity just because two headlines start with "🍻 FiniteBrews: " for example.

    RETURNS
    List of headlines after de-duplication
    """
    try:
        # Validate that the local model exists
        if not os.path.exists(smart_dedup_config["path_to_model"]):
            logging.warning(
                f"""
                Smart deduper failed. Local path to model doesn't exist. See README.md for setup.
                
                path_to_model: {smart_dedup_config['path_to_model']}
                """
            )
            return headlines

        # Load it
        model = SentenceTransformer(smart_dedup_config["path_to_model"])

        # First, temporarily remove prefaces to headlines.
        # TODO: Refactor so that FiniteNews doesn't add prefaces until after editing. Then we can avoid this hokey pokey move.
        headlines_clean = headlines
        for preface in set(prefaces_to_ignore):
            headlines_clean = [h.replace(preface, "").strip() for h in headlines_clean]
        logging.info(f"Smart_deduper prefaces to ignore: {set(prefaces_to_ignore)}")

        # Second, find pairs of headlines that are semantically similar
        # We'll get their sentence embeddings and use cosine_similarity

        embeddings = model.encode(headlines_clean, convert_to_tensor=True)
        similarity_matrix = cos_sim(embeddings, embeddings)

        dups_found = [
            # Get every unique combination of headlines...
            [headlines[i], headlines[j]]
            for i in range(embeddings.shape[0])
            for j in range(embeddings.shape[0])
            # ...if their semanatic similarity meets threshold
            if similarity_matrix[i, j] >= smart_dedup_config["threshold"]
            # ...and a headlines isn't being compared to itself
            and i != j
        ]

        if not dups_found:
            logging.info("Smart deduper: no semantic dups found")
            return headlines

        # Third, apply the transitive property of headline similarity! :D
        # Given pairs of headlines flagged as semantically similar, find the minimum set of unique items.
        # We assume if (headline A similar to headline B) and (B similar to C), we keep A and drop B and C

        # Initialize by de-duplicating first pair of items. Keep first in pair, drop second
        keepers = {dups_found[0][0]}
        droppers = {dups_found[0][1]}
        for pair in dups_found[1:]:  # Then walk through the rest of the pairs
            # Have we already flagged at least one item in the pair as a keeper or a dropper?
            if set(pair).intersection(keepers.union(droppers)):
                # Find the unseen item(s) and drop it (them).
                # By transitive property, it's similar to a seen item so we won't keep it.
                if pair[0] not in droppers and pair[0] not in keepers:
                    droppers.add(pair[0])
                if pair[1] not in droppers and pair[1] not in keepers:
                    droppers.add(pair[1])
            # Have we never seen either item in the new pair before?
            else:
                # Keep the first, drop the second
                keepers.add(pair[0])
                droppers.add(pair[1])

        # Finally, map the headlines to drop to the full headline including preface.
        # Droppers won't change if prefaces_to_ignore is empty.
        droppers = [h for h in headlines for d in droppers if d in h]

        logging.info(
            f"Smart dededuper found the following pairs of headlines that met threshold: {dups_found}"
        )
        logging.info(f"Smart deduper kept: {keepers}. Removed: {droppers}")
        return [h for h in headlines if h not in droppers]

    except Exception as e:
        logging.warning(f"Smart deduper failed: {str(type(e))}, {str(e)}")
        return headlines


def openai_chat_completion(gpt_config, message):
    """Make an API call to the OpenAI GPT chat endpoint.

    ARGUMENTS
    gpt_config (dict): Parameters for using the API
    message (str): The full prompt to send GPT, including generic lead-in, headlines, and instruction (customized to each subscriber)

    RETURNS
    GPT's response of which headlines to remove, in str format
    """

    response = openai.ChatCompletion.create(
        model=gpt_config["substance_filter_model"],
        messages=[
            {"role": "system", "content": gpt_config["system_role"]},
            {"role": "user", "content": message},
        ],
    )
    return response["choices"][0]["message"]["content"]


def apply_substance_filter_model(headlines, gpt_config):
    """Use LLM to remove headlines that don't say much useful.

    NOTE
    Requires a secret/environment variable for OPENAI_API_KEY. See README.md.

    ARGUMENTS
    headlines (list): List of string headlines, original candidates for the issue
    gpt_config (dict): Configuration for editing headlines using GPT LLM through the Open AI API.

    RETURNS
    List of headlines that GPT did not remove
    """

    GPT_RETRY_SLEEP = 30
    openai.api_key = get_fn_secret("OPENAI_API_KEY")
    headlines_for_gpt = [f"* {headline}" for headline in headlines]
    lead_in = "Here are today's news headlines:"
    message = (
        lead_in + "\n" + "\n".join(headlines_for_gpt) + "\n" + gpt_config["instruction"]
    )
    try:
        try:
            headlines_to_remove_str = openai_chat_completion(gpt_config, message)
        except openai.error.APIConnectionError:
            logging.info(
                f"OpenAI API error. Waiting {GPT_RETRY_SLEEP} secs, retrying..."
            )
            sleep(GPT_RETRY_SLEEP)
            headlines_to_remove_str = openai_chat_completion(gpt_config, message)
            logging.info(
                f"OpenAI API error. Waiting {GPT_RETRY_SLEEP} secs, retrying..."
            )
            logging.info("Retry worked! 😅")
    except Exception as e:
        logging.warning(f"OpenAI failed: {str(type(e))}, {str(e)}")
        headlines_to_remove_str = None

    headlines_to_remove = [h for h in headlines_to_remove_str.split("\n")]
    # Extra QC step to make sure GPT didn't return a hallucination that wasn't in headlines we sent it.
    removed_headlines = [
        headline for headline in headlines if headline in headlines_to_remove
    ]
    logging.warning(f"GPT removed: {removed_headlines}")
    return [headline for headline in headlines if headline not in removed_headlines]


def clean_headline(headline, enforce_trailing_period=True):
    """Standardize text formatting of a headline string

    NOTE
    - Assumes we have already stripped white space from beginning and end of headline
    - We apply these steps before applying substance rules, which rely on standard format,
    before checking if these headlines were in the last issue, and before caching this issue's headlines.

    ARGUMENTS
    headline (str): A single headline.
    enforce_trailing_period (bool): Whether to ensure headlines end in a period. True for news and alerts. False for image sections.

    RETURNS
    A single, clean headline as str
    """

    headline = (
        headline.replace("’", "'")  # Standardize apostrophe characters
        .replace("‘", "'")
        .replace("\xa0", " ")  # Non-breaking space unicode
    )
    if enforce_trailing_period:
        # Ensure all have trailing period
        headline = (
            headline + "."
            if not headline.endswith(".")
            and not (headline.endswith("?") or headline.endswith("!"))
            else headline
        )
    return headline


def edit_headlines(
    raw_headlines,
    issue_config,
    filter_for_substance=True,
    smart_deduplicate=True,
    enforce_trailing_period=True,
    sources_type="news_sources",
):
    """Apply all editorial policies to the headlines.

    ARGUMENTS
    raw_headlines (list): List of string headlines, original candidates for the issue
    issue_config (dict): The settings for the issue
    filter_for_substance (bool): Apply rules ± LLM to remove non-substantive headlines
    smart_deduplicate (bool): When headlines have similar meaning, only keep one in the set.
    enforce_trailing_period (bool): Whether to ensure headlines end in a period. True for news and alerts. False for image sections.
    sources_type (str): The name of the key in issue_config to get the lists of sources for these headlines, so we can find their prefaces used.

    RETURNS
    List of headlines after filtering ones that violate editorial policies
    """

    if not raw_headlines:
        return raw_headlines
    # Apply deterministic cleaning first
    edited_headlines = remove_items_in_last_issue(
        raw_headlines,
        issue_config["editorial"]["cache_path"],
    )
    edited_headlines = [
        clean_headline(headline, enforce_trailing_period)
        for headline in edited_headlines
    ]  # Do after removing repeats, since we cache the raw uncleaned
    for keyword in issue_config["editorial"]["one_headline_keywords"]:
        # NOTE: No list comprehension because each cycle can change edited_headlines
        edited_headlines = apply_one_headline_keyword_filter(edited_headlines, keyword)
    if edited_headlines and filter_for_substance:
        edited_headlines = apply_substance_rules(
            edited_headlines, issue_config["editorial"]["substance_rules"]
        )
        # Then probablistic LLM cleaning
        # Start with substance filter model. Remove ones that aren't great headlines.
        if issue_config["editorial"]["gpt"]:
            edited_headlines = apply_substance_filter_model(
                edited_headlines, issue_config["editorial"]["gpt"]
            )
        else:
            logging.info("Did not apply LLM substance model. GPT not configured.")
    # Finally, smart deduplicate (by semantic similarity) the remaining headlines that are individually fine options.
    if (
        edited_headlines
        and smart_deduplicate
        and issue_config["editorial"]["smart_deduper"]
    ):
        prefaces_to_ignore = [
            source.get("preface", None) for source in issue_config[sources_type]
        ]
        prefaces_to_ignore = [p for p in prefaces_to_ignore if p]
        edited_headlines = smart_dedup(
            edited_headlines,
            issue_config["editorial"]["smart_deduper"],
            prefaces_to_ignore,
        )
    logging.info("Edited headlines: " + str(edited_headlines))
    return edited_headlines
