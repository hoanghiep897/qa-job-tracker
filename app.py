"""Streamlit MVP dashboard with clear demo-data labeling."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from tracker.core import connect

st.set_page_config(page_title="QA Job Tracker", page_icon="📊", layout="wide")
st.title("QA Job Market Tracker")
st.caption("Lightweight job market explorer • Python + SQLite • No paid AI API")
db_path = "data/jobs.db"
if not Path(db_path).exists():
    st.info("No data yet. Run `python -m tracker.cli seed-demo` or import real JD data.")
    st.stop()

db = connect(db_path)
data = pd.read_sql_query("SELECT * FROM jobs ORDER BY first_seen DESC", db)
if data.empty:
    st.info("Database is empty. Collect jobs or import CSV to get started.")
    st.stop()
data["skills"] = data["skills_json"].map(json.loads)
if bool(data["demo"].any()):
    st.warning("Demo records are present. These are synthetic examples, NOT real hiring statistics.")
include_demo = st.toggle("Show demo records", value=not bool((data["demo"] == 0).any()))
if not include_demo:
    data = data[data["demo"] == 0]
if data.empty:
    st.info("No records match. Enable demo records or import real jobs.")
    st.stop()
roles = sorted(data["role"].dropna().unique())
locations = sorted(x for x in data["location"].dropna().unique() if x)
c1, c2 = st.columns(2)
selected_roles = c1.multiselect("Roles", roles, default=roles)
selected_locations = c2.multiselect("Locations (blank = all)", locations)
filtered = data[data["role"].isin(selected_roles)]
if selected_locations:
    filtered = filtered[filtered["location"].isin(selected_locations)]
if filtered.empty:
    st.info("No jobs match these filters.")
    st.stop()
a,b,c = st.columns(3)
a.metric("Job records", len(filtered))
b.metric("Companies", filtered["company"].nunique())
c.metric("Sources", filtered["source"].nunique())
st.subheader("Roles")
st.bar_chart(filtered["role"].value_counts())
st.subheader("Skills mentioned")
skill_counts = filtered.explode("skills")["skills"].dropna().value_counts()
if len(skill_counts):
    st.bar_chart(skill_counts)
else:
    st.info("No recognized skills in this selection.")
st.subheader("JD Explorer")
show = filtered[["title","company","location","role","source","url","skills"]].copy()
show["skills"] = show["skills"].map(lambda s: ", ".join(s))
st.dataframe(show, hide_index=True, use_container_width=True, column_config={"url": st.column_config.LinkColumn("JD source")})
st.download_button("Download filtered CSV", show.to_csv(index=False).encode("utf-8-sig"), "qa_jobs.csv", "text/csv")
st.caption("Job records are source observations, not a validated estimate of all open positions. Deduplication across sites is not yet implemented.")
