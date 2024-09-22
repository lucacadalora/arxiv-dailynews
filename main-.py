import gradio as gr
import arxiv
import threading
from datetime import datetime, timezone
from collections import defaultdict
import time
# Uncomment the following lines if you choose to implement disk-based caching
# import pickle
# import os

# List of selected arXiv main categories
CATEGORIES = [
    'physics',    # Includes all physics subcategories (e.g., astro-ph, cond-mat)
    'math',       # Includes all mathematics subcategories (e.g., math-ph)
    'cs',         # Includes all computer science subcategories
    'q-bio',      # Quantitative Biology
    'q-fin',      # Quantitative Finance
    'stat',       # Statistics
    'eess',       # Electrical Engineering and Systems Science
    'econ'        # Economics
]

class PaperManager:
    def __init__(self, papers_per_page=30):
        self.papers_per_page = papers_per_page
        self.current_page = 1
        self.papers = []
        self.total_pages = 1
        self.sort_method = "hot"  # Default sort method
        self.trending_keywords = []
        self.author_publication_counts = defaultdict(int)
        self.all_past_papers = []  # Papers from past for analysis
        self.new_papers = []       # Latest papers for "New" category
        self.lock = threading.Lock()
        self.last_fetch_time = None  # Timestamp of the last data fetch
        self.cache_duration = 3600   # Cache duration in seconds (1 hour)
        # Uncomment the following line if you choose to implement disk-based caching
        # self.cache_file = 'cached_papers.pkl'

    def fetch_papers_async(self):
        # Check if we have recent data
        if self.last_fetch_time and (time.time() - self.last_fetch_time) < self.cache_duration:
            print("Using cached data.")
            return True

        # Uncomment the following block if you choose to implement disk-based caching
        """
        # Check if cache file exists and is recent
        if os.path.exists(self.cache_file):
            file_mod_time = os.path.getmtime(self.cache_file)
            if (time.time() - file_mod_time) < self.cache_duration:
                print("Loading data from cache file.")
                with open(self.cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                self.all_past_papers = cached_data['all_past_papers']
                self.new_papers = cached_data['new_papers']
                self.calculate_trending_keywords()
                self.calculate_author_activity()
                self.raw_papers = self.all_past_papers
                self.sort_papers()
                self.total_pages = max((len(self.papers) + self.papers_per_page - 1) // self.papers_per_page, 1)
                self.current_page = 1
                return True
        """

        # Proceed to fetch data asynchronously
        threads = []
        threads.append(threading.Thread(target=self.fetch_past_papers))
        threads.append(threading.Thread(target=self.fetch_new_papers))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        if not self.all_past_papers or not self.new_papers:
            print("Failed to fetch papers.")
            return False

        # Proceed to process data
        self.calculate_trending_keywords()
        self.calculate_author_activity()
        self.raw_papers = self.all_past_papers
        self.sort_papers()
        self.total_pages = max((len(self.papers) + self.papers_per_page - 1) // self.papers_per_page, 1)
        self.current_page = 1
        self.last_fetch_time = time.time()  # Update the last fetch time

        # Uncomment the following block if you choose to implement disk-based caching
        """
        # Save data to cache file
        with open(self.cache_file, 'wb') as f:
            pickle.dump({
                'all_past_papers': self.all_past_papers,
                'new_papers': self.new_papers
            }, f)
        """

        return True

    def fetch_past_papers(self):
        try:
            past_papers = {}
            for category in CATEGORIES:
                try:
                    search_past = arxiv.Search(
                        query=f"cat:{category}.*",
                        max_results=100,  # Increased to 100 per category
                        sort_by=arxiv.SortCriterion.SubmittedDate,
                        sort_order=arxiv.SortOrder.Descending,
                    )
                    for paper in search_past.results():
                        past_papers[paper.entry_id] = paper  # Avoid duplicates
                    time.sleep(1.25)  # Delay to respect rate limits
                except Exception as e:
                    print(f"Error fetching papers for category {category}: {e}")
            with self.lock:
                self.all_past_papers = list(past_papers.values())
        except Exception as e:
            print(f"Error in fetch_past_papers: {e}")

    def fetch_new_papers(self):
        try:
            new_papers = {}
            for category in CATEGORIES:
                try:
                    search_new = arxiv.Search(
                        query=f"cat:{category}.*",
                        max_results=100,  # Increased to 100 per category
                        sort_by=arxiv.SortCriterion.SubmittedDate,
                        sort_order=arxiv.SortOrder.Descending,
                    )
                    for paper in search_new.results():
                        new_papers[paper.entry_id] = paper  # Avoid duplicates
                    time.sleep(1.25)  # Delay to respect rate limits
                except Exception as e:
                    print(f"Error fetching new papers for category {category}: {e}")
            with self.lock:
                self.new_papers = list(new_papers.values())
        except Exception as e:
            print(f"Error in fetch_new_papers: {e}")

    def calculate_trending_keywords(self):
        # Extract keywords from past papers to identify trending topics
        keyword_counts = defaultdict(int)
        for paper in self.all_past_papers:
            # Combine title and abstract for keyword extraction
            text = (paper.title + ' ' + paper.summary).lower()
            words = text.split()
            for word in words:
                if len(word) > 4:  # Consider words longer than 4 letters
                    keyword_counts[word] += 1
        # Get the top 50 keywords
        sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
        self.trending_keywords = [word for word, count in sorted_keywords[:50]]

    def calculate_author_activity(self):
        # Count the number of papers each author has published in the past
        for paper in self.all_past_papers:
            for author in paper.authors:
                self.author_publication_counts[author.name] += 1

    def calculate_score(self, paper):
        """
        Enhanced Hotness score based on recency, author activity, and trending keywords.
        """
        published_time = paper.published.replace(tzinfo=timezone.utc)
        time_diff = datetime.now(timezone.utc) - published_time
        time_diff_days = max(time_diff.days, 0)  # Ensure non-negative days

        # Author activity score (sum of publications)
        author_activity_score = sum([self.author_publication_counts.get(author.name, 0) for author in paper.authors])

        # Keyword score
        keyword_score = 0
        text = (paper.title + ' ' + paper.summary).lower()
        for keyword in self.trending_keywords:
            if keyword in text:
                keyword_score += 1

        # Calculate the hotness score
        # Papers with active authors, trending keywords, and recency have higher scores
        score = (author_activity_score + keyword_score) / ((time_diff_days + 7) ** 1.5)
        return score

    def calculate_rising_score(self, paper):
        """
        Rising score focuses on novelty by identifying new keywords.
        """
        published_time = paper.published.replace(tzinfo=timezone.utc)
        time_diff = datetime.now(timezone.utc) - published_time
        time_diff_days = max(time_diff.days, 0)  # Ensure non-negative days

        # Novelty score (number of uncommon keywords)
        text = (paper.title + ' ' + paper.summary).lower()
        words = set(text.split())
        uncommon_keywords = words - set(self.trending_keywords)
        novelty_score = len(uncommon_keywords)

        # Rising score favors recent papers with novel content
        score = novelty_score / (time_diff_days + 1)
        return score

    def sort_papers(self):
        if self.sort_method == "hot":
            self.papers = sorted(
                self.raw_papers,
                key=lambda x: self.calculate_score(x),
                reverse=True
            )
        elif self.sort_method == "new":
            # Use the latest papers fetched specifically for "New" category
            self.papers = sorted(
                self.new_papers,
                key=lambda x: x.published,
                reverse=True
            )
        elif self.sort_method == "rising":
            self.papers = sorted(
                self.raw_papers,
                key=lambda x: self.calculate_rising_score(x),
                reverse=True
            )
        else:
            self.papers = sorted(
                self.raw_papers,
                key=lambda x: self.calculate_score(x),
                reverse=True
            )

    def set_sort_method(self, method):
        if method.lower() not in ["hot", "new", "rising"]:
            method = "hot"
        print(f"Setting sort method to: {method}")
        self.sort_method = method.lower()
        self.sort_papers()
        self.current_page = 1
        return True  # Assume success

    def format_paper(self, paper, rank):
        title = paper.title
        url = paper.pdf_url or paper.entry_id
        authors = ', '.join([author.name for author in paper.authors]) or 'Unknown'
        num_authors = len(paper.authors)
        published_time = paper.published.replace(tzinfo=timezone.utc)
        time_diff = datetime.now(timezone.utc) - published_time
        time_ago_days = time_diff.days
        time_ago = f"{time_ago_days} days ago" if time_ago_days > 0 else "today"
        categories = ', '.join(paper.categories) if paper.categories else 'Uncategorized'

        return f"""
        <tr class="athing">
            <td align="right" valign="top" class="title"><span class="rank">{rank}.</span></td>
            <td valign="top" class="title">
                <a href="{url}" class="storylink" target="_blank">{title}</a>
            </td>
        </tr>
        <tr>
            <td colspan="2" class="subtext">
                <span class="score">{num_authors} authors</span> | Categories: {categories} | Published: {published_time.strftime('%Y-%m-%d')} | {time_ago}
            </td>
        </tr>
        <tr class="spacer"><td colspan="2"></td></tr>
        """

    def render_papers(self):
        start = (self.current_page - 1) * self.papers_per_page
        end = start + self.papers_per_page
        current_papers = self.papers[start:end]

        if not current_papers:
            return "<div class='no-papers'>No papers available for this page.</div>"

        papers_html = "".join([self.format_paper(paper, idx + start + 1) for idx, paper in enumerate(current_papers)])
        return f"""
        <table border="0" cellpadding="0" cellspacing="0" class="itemlist">
            {papers_html}
        </table>
        """

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
        return self.render_papers()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
        return self.render_papers()

# Ensure global persistence of the PaperManager instance
paper_manager = PaperManager()

def initialize_app():
    # Display a loading message
    loading_message = "<div class='no-papers'>Fetching papers, please wait...</div>"
    yield loading_message

    if paper_manager.fetch_papers_async():
        yield paper_manager.render_papers()
    else:
        yield "<div class='no-papers'>Failed to fetch papers. Please try again later.</div>"

def change_sort_method(method):
    method_lower = method.lower()
    print(f"Changing sort method to: {method_lower}")
    if paper_manager.set_sort_method(method_lower):
        print("Sort method set successfully.")
        return paper_manager.render_papers()
    else:
        print("Failed to set sort method.")
        return "<div class='no-papers'>Failed to sort papers. Please try again later.</div>"

css = """
/* Hacker News-like CSS */

body {
    background-color: white;
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11px;
    color: #000;
    margin: 0;
    padding: 0;
}

a {
    color: #0000ff;
    text-decoration: none;
}

a:visited {
    color: #551a8b;
}

.container {
    width: 85%;
    margin: auto;
    padding-top: 10px;
}

.itemlist {
    width: 100%;
    border-collapse: collapse;
}

.header-table {
    width: 100%;
    background-color: #ff6600;
    padding: 2px 10px;
}

.header-table a {
    color: black;
    font-weight: bold;
    font-size: 14pt;
    text-decoration: none;
}

.athing {
    background-color: #f6f6ef;
}

.rank {
    font-size: 10px;
    color: #828282;
    padding-right: 5px;
}

.storylink {
    font-size: 13px;
    font-weight: bold;
}

.subtext {
    font-size: 10px;
    color: #828282;
    padding-left: 40px;
}

.subtext a {
    color: #828282;
    text-decoration: none;
}

.subtext a:hover {
    text-decoration: underline;
}

.spacer {
    height: 5px;
}

.no-papers {
    text-align: center;
    color: #828282;
    padding: 1rem;
    font-size: 14pt;
}

.pagination {
    padding: 10px 0;
    text-align: center;
}

.pagination button {
    background-color: #ff6600;
    border: 1px solid #ff6600;
    color: white;
    padding: 2px 6px;
    margin: 0 5px;
    cursor: pointer;
    font-size: 11px;
    border-radius: 3px;
}

.pagination button:hover {
    background-color: #e55b00;
}

.pagination button:disabled {
    background-color: #f0f0f0;
    color: #ccc;
    cursor: not-allowed;
}

.sort-radio {
    margin-bottom: 10px;
}

@media (max-width: 640px) {
    .header-table a {
        font-size: 12pt;
    }

    .storylink {
        font-size: 11px;
    }

    .subtext {
        font-size: 9px;
    }

    .rank {
        font-size: 9px;
    }

    .pagination button {
        padding: 2px 5px;
        font-size: 9px;
    }
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
    body {
        background-color: #121212;
        color: #e0e0e0;
    }

    a {
        color: #add8e6;
    }

    a:visited {
        color: #9370db;
    }

    .header-table {
        background-color: #333;
    }

    .header-table a {
        color: #e0e0e0;
    }

    .athing {
        background-color: #1e1e1e;
    }

    .rank {
        color: #b0b0b0;
    }

    .subtext {
        color: #b0b0b0;
    }

    .subtext a {
        color: #b0b0b0;
    }

    .no-papers {
        color: #b0b0b0;
    }

    .pagination button {
        background-color: #555;
        border: 1px solid #555;
    }

    .pagination button:hover {
        background-color: #666;
    }

    .pagination button:disabled {
        background-color: #333;
        color: #555;
    }
}

/* Footer Styles */
.footer {
    text-align: center;
    padding: 20px 0;
    color: #828282;
    font-size: 10px;
}

.footer a {
    color: #828282;
    text-decoration: none;
}

.footer a:hover {
    text-decoration: underline;
}
"""

demo = gr.Blocks(css=css, title="arXiv news")

with demo:
    with gr.Column(elem_classes=["container"]):
        # Accordion for Information
        with gr.Accordion("About This App", open=False):
            gr.Markdown("""
            This app displays recent papers from **arXiv** across selected fields.

            **Data Source:** The papers are fetched from the arXiv API.

            **Enhanced Scoring Algorithms:**
            - **Hot Score:** Considers recency, author activity (number of publications), and trending keywords extracted from recent papers.
            - **Rising Score:** Focuses on novelty by identifying papers with new or uncommon keywords compared to trending topics.

            **Note:** Since arXiv doesn't provide citation counts, download statistics, or social media mentions through their API, the scoring algorithms are approximated based on available metadata.

            **Please be patient:** Initial data fetching may take some time. Subsequent loads within an hour will be faster due to caching.
            """)
        # Header without Refresh Button
        with gr.Row():
            gr.HTML("""
            <table border="0" cellpadding="0" cellspacing="0" class="header-table">
                <tr>
                    <td>
                        <span class="pagetop">
                            <b class="hnname"><a href="#">Daily arXiv Papers</a></b>
                        </span>
                    </td>
                </tr>
            </table>
            """)
        # Sorting Options
        with gr.Column():
            sort_radio = gr.Radio(
                choices=["Hot", "New", "Rising"],
                value="Hot",
                label="",  # Remove the original label
                interactive=True,
                elem_classes=["sort-radio"]
            )
        # Paper list with loading message
        paper_list = gr.HTML()
        # Navigation Buttons
        with gr.Row(elem_classes=["pagination"]):
            prev_button = gr.Button("Prev")
            next_button = gr.Button("Next")
        # Footer
        with gr.Row():
            gr.HTML("""
            <div class="footer">
                ©️ 2024 <a href="https://x.com/lucaxyzz" target="_blank">lucaxyzz</a> 🦊
            </div>
            """)

    # Load papers on app start with a loading message
    demo.load(initialize_app, outputs=[paper_list])

    # Button clicks for pagination
    prev_button.click(paper_manager.prev_page, outputs=[paper_list])
    next_button.click(paper_manager.next_page, outputs=[paper_list])

    # Sort option change
    sort_radio.change(
        fn=change_sort_method,
        inputs=[sort_radio],
        outputs=[paper_list]
    )

demo.launch()
