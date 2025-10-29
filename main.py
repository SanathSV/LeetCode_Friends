# --------------------------------------------------------------
#  LeetCode Leaderboard – WITH SKILL FILTER
# --------------------------------------------------------------
import streamlit as st
import pandas as pd
import requests
import os
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --------------------- Config ---------------------
BASE = "https://alfa-leetcode-api.onrender.com"
CSV_FILE = "tracked_users.csv"
CACHE_TTL = 1800  # 30 minutes

# Skill level order: Advanced (top) to Intermediate to Fundamental
LEVEL_ORDER = {"Advanced": 0, "Intermediate": 1, "Fundamental": 2}

# --------------------- Utilities ---------------------
def init_csv():
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=["username", "added_at"]).to_csv(CSV_FILE, index=False)

def load_users() -> pd.DataFrame:
    init_csv()
    df = pd.read_csv(CSV_FILE)
    if "added_at" not in df.columns:
        df["added_at"] = pd.NaT
    return df

def save_users(df: pd.DataFrame):
    df.to_csv(CSV_FILE, index=False)

def add_user(username: str) -> bool:
    df = load_users()
    username = username.strip()
    if username and username not in df["username"].values:
        new_row = pd.DataFrame([{"username": username, "added_at": pd.Timestamp.now()}])
        df = pd.concat([df, new_row], ignore_index=True)
        save_users(df)
        return True
    return False

def remove_user(username: str):
    df = load_users()
    df = df[df["username"] != username]
    save_users(df)

# --------------------- API Calls ---------------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_profile(username: str) -> dict | None:
    try:
        r = requests.get(f"{BASE}/userProfile/{username}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Profile error ({username}): {e}")
        return None

def compute_accuracy(profile: dict) -> float:
    try:
        ac = profile["matchedUserStats"]["acSubmissionNum"]
        total = profile["matchedUserStats"]["totalSubmissionNum"]
        for a, t in zip(ac, total):
            if a["difficulty"] == "All":
                sub = t["submissions"]
                return round(a["submissions"] / sub * 100, 2) if sub else 0.0
    except Exception:
        pass
    return 0.0

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_skill_table(username: str) -> pd.DataFrame:
    try:
        r = requests.get(f"{BASE}/{username}/skill", timeout=10)
        r.raise_for_status()
        data = r.json()
        records = []
        for level_raw, skills in data.items():
            level = level_raw.capitalize()
            if level not in LEVEL_ORDER:
                level = "Fundamental"  # fallback
            if isinstance(skills, list):
                for s in skills:
                    records.append({
                        "Level": level,
                        "Skill": s.get("tagName", "Unknown"),
                        "Problems Solved": s.get("problemsSolved", 0),
                        "Username": username,
                        "_sort": LEVEL_ORDER.get(level, 2)
                    })
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values(["_sort", "Problems Solved"], ascending=[True, False])
        return df.drop(columns=["_sort"])
    except Exception as e:
        st.error(f"Skill error ({username}): {e}")
        return pd.DataFrame()

def rank_change(old, new):
    if pd.isna(old) or old == "N/A":
        return ""
    diff = old - new
    if diff > 0:
        return f"Up {diff}"
    if diff < 0:
        return f"Down {-diff}"
    return "No change"

# --------------------- Session State ---------------------
if "prev_ranks" not in st.session_state:
    st.session_state.prev_ranks = {}

# --------------------- UI Setup ---------------------
st.set_page_config(page_title="LeetCode Leaderboard", layout="wide")
st.title("LeetCode Leaderboard")

# ---------- Sidebar: User Management ----------
st.sidebar.header("Manage Users")
bulk_input = st.sidebar.text_input("Add username(s) – comma separated:")
if st.sidebar.button("Add User(s)"):
    if bulk_input.strip():
        added = []
        for u in [x.strip() for x in bulk_input.split(",") if x.strip()]:
            if add_user(u):
                added.append(u)
        if added:
            st.sidebar.success(f"Added: {', '.join(added)}")
            st.rerun()
        else:
            st.sidebar.warning("All usernames already exist.")
    else:
        st.sidebar.error("Enter at least one username.")

if st.sidebar.button("Refresh All (clear cache)"):
    st.cache_data.clear()
    st.session_state.prev_ranks = {}
    st.rerun()

# ---------- Load Users ----------
users_df = load_users()
if users_df.empty:
    st.info("No users tracked yet. Add usernames in the sidebar.")
    st.stop()

usernames = users_df["username"].tolist()

# ---------- Fetch Data ----------
progress = st.progress(0)
rows, skill_dfs = [], []

for i, user in enumerate(usernames):
    progress.progress((i + 1) / len(usernames))
    with st.spinner(f"Fetching {user}…"):
        prof = get_profile(user)
        if prof:
            rows.append({
                "Username": user,
                "Total Solved": prof.get("totalSolved", 0),
                "Easy": prof.get("easySolved", 0),
                "Medium": prof.get("mediumSolved", 0),
                "Hard": prof.get("hardSolved", 0),
                "Accuracy %": compute_accuracy(prof),
                "Rank": prof.get("ranking", "N/A"),
                "Rank Delta": rank_change(st.session_state.prev_ranks.get(user), prof.get("ranking")),
            })
            skill_dfs.append(get_skill_table(user))
        st.session_state.prev_ranks[user] = prof.get("ranking") if prof else "N/A"

progress.empty()

if not rows:
    st.warning("No data fetched. Check usernames or internet connection.")
    st.stop()

df = pd.DataFrame(rows).sort_values("Total Solved", ascending=False)
df.index = range(1, len(df) + 1)

# ---------- Leaderboard ----------
st.subheader("Leaderboard")
c1, c2 = st.columns([4, 1])
with c1:
    st.dataframe(df.drop(columns=["Rank Delta"]), hide_index=False, use_container_width=True)
with c2:
    csv = df.to_csv(index=False).encode()
    st.download_button("Export CSV", csv, "leetcode_leaderboard.csv", "text/csv")

# Rank changes
if any(df["Rank Delta"]):
    st.markdown("#### Rank Changes")
    st.dataframe(df[df["Rank Delta"] != ""][["Username", "Rank Delta"]], hide_index=True)

# ---------- Charts ----------
tab1, tab2, tab3 = st.tabs(["Total Solved", "Difficulty Split", "Accuracy"])

with tab1:
    fig = px.bar(df, x="Username", y="Total Solved", text="Total Solved",
                 title="Total Problems Solved", color="Total Solved",
                 color_continuous_scale="Viridis")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    diff_df = df.melt(id_vars="Username", value_vars=["Easy", "Medium", "Hard"],
                      var_name="Difficulty", value_name="Solved")
    fig = px.bar(diff_df, x="Username", y="Solved", color="Difficulty",
                 title="Problems Solved by Difficulty",
                 color_discrete_map={"Easy": "#2ca02c", "Medium": "#ff7f0e", "Hard": "#d62728"})
    fig.update_layout(barmode="stack")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Per-user pie charts"):
        for user in df["Username"]:
            user_row = df[df["Username"] == user][["Easy", "Medium", "Hard"]].iloc[0]
            fig_pie = px.pie(values=user_row.values, names=user_row.index,
                             title=f"{user} – Difficulty")
            st.plotly_chart(fig_pie, use_container_width=True)

with tab3:
    fig = px.bar(df, x="Username", y="Accuracy %", text="Accuracy %",
                 title="Submission Accuracy", color="Accuracy %",
                 color_continuous_scale="Blues")
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

# ---------- NEW: Skill Filter & Filtered Tables ----------
st.subheader("Skill Comparison")

# Collect all unique skills
all_skills = pd.concat(skill_dfs, ignore_index=True) if skill_dfs else pd.DataFrame()
if not all_skills.empty:
    unique_skills = sorted(all_skills["Skill"].unique(), key=lambda x: (-all_skills[all_skills["Skill"] == x]["Problems Solved"].sum(), x))
    
    # Skill filter dropdown
    selected_skill = st.selectbox(
        "Filter by Skill (leave empty for all):",
        options=["All Skills"] + unique_skills,
        index=0,
        help="Select a specific skill to compare across all users"
    )
    
    # Filter skills data
    filtered_skills = all_skills if selected_skill == "All Skills" else all_skills[all_skills["Skill"] == selected_skill]
    
    if not filtered_skills.empty:
        # Add sort key for level ordering
        filtered_skills["_sort"] = filtered_skills["Level"].map(LEVEL_ORDER).fillna(2)
        filtered_skills = filtered_skills.sort_values(["_sort", "Problems Solved"], ascending=[True, False])
        
        # Create comparison table: rows=users, columns=skills, values=problems solved
        if selected_skill == "All Skills":
            # Show top skills per user (grouped by level)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Advanced Skills**")
                adv_skills = filtered_skills[filtered_skills["Level"] == "Advanced"].head(5)
                if not adv_skills.empty:
                    st.dataframe(adv_skills[["Username", "Skill", "Problems Solved"]], hide_index=True)
            
            with col2:
                st.markdown("**Intermediate/Fundamental**")
                other_skills = filtered_skills[filtered_skills["Level"].isin(["Intermediate", "Fundamental"])].head(5)
                if not other_skills.empty:
                    st.dataframe(other_skills[["Username", "Skill", "Problems Solved"]], hide_index=True)
        else:
            # Single skill comparison table
            skill_pivot = filtered_skills.pivot_table(
                index="Username",
                values="Problems Solved",
                aggfunc="sum",
                fill_value=0
            ).sort_values("Problems Solved", ascending=False)
            
            st.markdown(f"**{selected_skill} – Problems Solved by User**")
            st.dataframe(skill_pivot, hide_index=False, use_container_width=True)
            
            # Bar chart for this skill
            fig = px.bar(skill_pivot.reset_index(), x="Username", y="Problems Solved",
                        title=f"{selected_skill} Comparison",
                        color="Problems Solved", color_continuous_scale="Viridis")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available for selected filter.")
else:
    st.info("No skill data available.")

# ---------- Original Skill Heatmap (Unfiltered) ----------
with st.expander("Full Skill Heatmap (All Skills)"):
    st.markdown("**Skill Strength Heatmap (Advanced to Fundamental)**")
    if not all_skills.empty:
        all_skills["_sort"] = all_skills["Level"].map(LEVEL_ORDER).fillna(2)
        pivot = all_skills.pivot_table(
            index=["Skill", "Level", "_sort"],
            columns="Username",
            values="Problems Solved",
            aggfunc="sum",
            fill_value=0
        ).reset_index()
        pivot = pivot.sort_values("_sort").drop(columns="_sort")
        y_labels = pivot["Skill"] + " (" + pivot["Level"] + ")"

        fig = go.Figure(data=go.Heatmap(
            z=pivot.drop(columns=["Skill", "Level"]).values,
            x=pivot.columns[2:],
            y=y_labels,
            colorscale="YlGnBu",
            text=pivot.drop(columns=["Skill", "Level"]).values,
            texttemplate="%{text}",
            textfont=dict(size=10)
        ))
        fig.update_layout(title="Problems Solved per Skill", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No skill data available.")

# ---------- Detailed per-user skill tables ----------
with st.expander("Detailed per-user skill tables"):
    for user in df["Username"]:
        usr = all_skills[all_skills["Username"] == user].copy()
        if not usr.empty:
            usr["_sort"] = usr["Level"].map(LEVEL_ORDER).fillna(2)
            usr = usr.sort_values(["_sort", "Problems Solved"], ascending=[True, False])
            st.markdown(f"**{user}**")
            st.dataframe(usr.drop(columns=["Username", "_sort"]), hide_index=True)

# ---------- Sidebar: Tracked Users List ----------
st.sidebar.markdown("---")
st.sidebar.subheader("Tracked Users")
edited = st.sidebar.data_editor(
    users_df.copy(),
    num_rows="dynamic",
    column_config={
        "username": st.column_config.TextColumn("Username", required=True),
        "added_at": st.column_config.DatetimeColumn("Added", disabled=True)
    },
    hide_index=True
)

if not edited.equals(users_df):
    save_users(edited)
    st.sidebar.success("User list updated!")
    st.rerun()

# Remove buttons
for user in users_df["username"]:
    c1, c2 = st.sidebar.columns([3, 1])
    c1.write(user)
    if c2.button("Remove", key=f"rm_{user}"):
        remove_user(user)
        st.rerun()