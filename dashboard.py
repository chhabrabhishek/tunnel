import streamlit as st
import pandas as pd
import requests
import time
import threading
from datetime import datetime, timedelta

st.set_page_config(layout="wide")

# List of API endpoints to monitor
API_ENDPOINTS = [
    "http://localhost:3000/mongo?env=dev&server=rp000123304.uhc.com&port=42395",
    "http://localhost:3000/oracle?env=mt_tst2",
    "http://localhost:3000/mysql?env=mt_tst",
    "http://localhost:3000/rabbitmq?env=dev&server=rn000140789.uhc.com&port=5672",
    "http://localhost:3000/rabbitmq/nodes?env=dev&server=rn000140789.uhc.com&port=15672",
]

# Interval between requests (in seconds)
INTERVAL = 10


# Shared data structure
class ResultStore:
    def __init__(self):
        self.results = []
        self.lock = threading.Lock()
        self.batch_count = 0

    def add_batch(self, batch):
        with self.lock:
            self.results.extend(batch)
            self.batch_count += 1

    def get_results(self):
        with self.lock:
            return list(self.results)


# Lock for thread-safe operations
lock = threading.Lock()


def start_polling(store):
    def poll_endpoints():
        while True:
            batch = []
            status = None
            error = None
            for endpoint in API_ENDPOINTS:
                start_time = time.time()
                try:
                    response = requests.get(endpoint)
                    status = "ok" if response.json()["ok"] else "not ok"
                except Exception as e:
                    error = f"Error: {e}"
                end_time = time.time()
                response_time = round(end_time - start_time, 3)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                batch.append(
                    {
                        "timestamp": timestamp,
                        "endpoint": endpoint.split("3000/")[1],
                        "status": status if status else error,
                        "response_time": response_time,
                        "response": (response.json() if status else error),
                    }
                )
            store.add_batch(batch)
            time.sleep(INTERVAL)

    thread = threading.Thread(target=poll_endpoints, daemon=True)
    thread.start()
    return store


@st.cache_resource
def get_store():
    store = ResultStore()
    return start_polling(store)


# Get the shared store
store = get_store()

st.sidebar.write(f"Total records: {len(store.get_results())}")
st.sidebar.write(f"Total batches collected: {store.batch_count}")

if "refresh_trigger" not in st.session_state:
    st.session_state.refresh_trigger = 0

data = store.get_results()

if not data or "timestamp" not in data[0]:
    st.info("Waiting for data or timestamp field is missing...")
    st.stop()


df = pd.DataFrame(data)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"])

latest_timestamp = df["timestamp"].max()
default_start = latest_timestamp - timedelta(minutes=30)

if "time_filter_initialized" not in st.session_state:
    st.session_state.start_date = default_start.date()
    st.session_state.start_time = default_start.time()
    st.session_state.end_date = latest_timestamp.date()
    st.session_state.end_time = latest_timestamp.time()
    st.session_state.time_filter_initialized = True

if st.button("🔄 Refresh Dashboard"):
    st.session_state.refresh_trigger += 1

    new_latest = df["timestamp"].max()
    old_latest = datetime.combine(st.session_state.end_date, st.session_state.end_time)

    if new_latest > old_latest:
        default_start = new_latest - timedelta(minutes=30)
        st.session_state.start_date = default_start.date()
        st.session_state.start_time = default_start.time()
        st.session_state.end_date = new_latest.date()
        st.session_state.end_time = new_latest.time()
    else:
        st.info("No new data since last refresh.")

st.sidebar.subheader("Time Range Filter")

if st.sidebar.button("📅 Use Last 30 Minutes"):
    st.session_state.start_date = default_start.date()
    st.session_state.start_time = default_start.time()
    st.session_state.end_date = latest_timestamp.date()
    st.session_state.end_time = latest_timestamp.time()


start_date = st.sidebar.date_input("Start Date", value=st.session_state.start_date)
start_time = st.sidebar.time_input("Start Time", value=st.session_state.start_time)
end_date = st.sidebar.date_input("End Date", value=st.session_state.end_date)
end_time = st.sidebar.time_input("End Time", value=st.session_state.end_time)

st.session_state.start_date = start_date
st.session_state.start_time = start_time
st.session_state.end_date = end_date
st.session_state.end_time = end_time

start_datetime = datetime.combine(start_date, start_time)
end_datetime = datetime.combine(end_date, end_time)

filtered_df = df[
    (df["timestamp"] >= start_datetime) & (df["timestamp"] <= end_datetime)
]

safe_df = filtered_df.copy()
if "response" in safe_df.columns:
    safe_df["response"] = safe_df["response"].astype(str)

st.title("Health Status Monitoring Service (HSMS) Dashboard")

if safe_df.empty:
    if len(df) > 0:
        st.warning("No data available in the selected time range.")
    else:
        st.info("Waiting for data...")

else:
    st.subheader("Latest Results")
    st.dataframe(safe_df)

    styled_df = safe_df.tail(10).style.apply(
        lambda row: [
            (
                "background-color: #d4edda; color: black"
                if row["status"] == "ok"
                else (
                    "background-color: #f8d7da; color: black"
                    if col == "endpoint"
                    else ""
                )
            )
            for col in row.index
        ],
        axis=1,
    )
    st.dataframe(styled_df)

    st.subheader("Current Health Count")
    st.bar_chart(safe_df["status"].value_counts())

    st.subheader("Endpoint Failure Frequency (All Time)")
    failure_counts = safe_df[safe_df["status"] != "ok"]["endpoint"].value_counts()
    st.bar_chart(failure_counts)

    st.subheader("Average Response Time per Endpoint")
    avg_response = safe_df.groupby("endpoint")["response_time"].mean()
    st.bar_chart(avg_response)

    st.subheader("Status Code Heatmap")
    heatmap_data = safe_df.pivot_table(
        index="timestamp",
        columns="endpoint",
        values="status",
        aggfunc="first",
    )
    st.dataframe(heatmap_data.style.background_gradient(cmap="RdYlGn", axis=None))
