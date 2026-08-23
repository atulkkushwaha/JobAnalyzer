import streamlit as st
import pandas as pd
from datetime import date
import database as db  # all DB logic lives in database.py
import analyzer  # skill-matching job description analyzer (no AI/API)

# ---- Page setup ----
st.set_page_config(page_title="Job Application Tracker", layout="wide")
st.title("📋 Job Application Tracker")

STAGES = ["Applied", "OA", "Interview", "Offer", "Rejected"]

# ---- Ensure table exists (runs once per session, harmless if repeated) ----
db.create_table()

# ---- Sidebar: filters (for Applications tab) ----
st.sidebar.header("Filters")
stage_filter = st.sidebar.selectbox("Filter by Stage", ["All"] + STAGES)
search_term = st.sidebar.text_input("Search by Company or Role")

# ---- Sidebar: user's own skills (for AI Job Analyzer tab) ----
st.sidebar.header("Your Skills")
user_skills_text = st.sidebar.text_area(
    "List your skills (comma or newline separated)",
    placeholder="python, sql, docker, react",
    height=100,
)

# ---- Sidebar: analysis mode toggle (for AI Job Analyzer tab) ----
analysis_mode = st.sidebar.radio(
    "Analysis Mode",
    ["Keyword Matching", "AI (Gemini)", "AI (Groq)"],
    help="Keyword Matching runs locally. The AI modes call an external API "
         "and fall back to Keyword Matching if that call is unavailable.",
)

# ---- Sidebar form to add a new application ----
st.sidebar.header("Add New Application")

with st.sidebar.form("add_application_form", clear_on_submit=True):
    company = st.text_input("Company")
    role = st.text_input("Role")
    salary = st.text_input("Salary (e.g. $120,000)")
    stage = st.selectbox("Stage", STAGES)
    date_applied = st.date_input("Date Applied", value=date.today())
    job_link = st.text_input("Job Link")

    submitted = st.form_submit_button("Add Application")

    if submitted:
        if company and role:  # basic validation, require at least company + role
            db.add_application(
                company, role, salary, stage,
                date_applied.strftime("%Y-%m-%d"), job_link,
            )
            st.sidebar.success(f"Added application for {role} at {company}")
        else:
            st.sidebar.error("Company and Role are required.")

# ---- Main area: two tabs ----
tab_applications, tab_analyzer = st.tabs(["Applications", "AI Job Analyzer"])

with tab_applications:
    # ---- Dashboard cards (counting logic lives in database.py) ----
    stats = db.get_stats()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Applications", stats["total"])
    col2.metric("Interviews", stats["interviews"])
    col3.metric("Offers", stats["offers"])
    col4.metric("Response Rate", f"{stats['response_rate']}%")

    st.divider()

    # ---- Display applications from the database (filtered) ----
    st.header("Your Applications")

    rows = db.get_all_applications(stage_filter=stage_filter, search=search_term)

    if len(rows) == 0:
        if stats["total"] == 0:
            st.info("No applications added yet. Use the sidebar form to add one.")
        else:
            st.info("No applications match the current filter/search.")
    else:
        # Show as a table for a clean overview
        df = pd.DataFrame(
            rows, columns=["ID", "Company", "Role", "Salary", "Stage", "Date Applied", "Job Link"]
        )
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True)

        # Also show each application as an expandable card with update/delete controls
        st.subheader("Details")
        for row in rows:
            app_id, company, role, salary, stage, applied_on, link = row
            with st.expander(f"{company} — {role} ({stage})"):
                st.write(f"**Salary:** {salary}")
                st.write(f"**Date Applied:** {applied_on}")
                if link:
                    st.write(f"**Job Link:** {link}")

                # Update stage dropdown
                new_stage = st.selectbox(
                    "Update Stage", STAGES, index=STAGES.index(stage), key=f"stage_{app_id}"
                )
                if new_stage != stage:
                    db.update_stage(app_id, new_stage)
                    st.rerun()

                # Delete button
                if st.button("Delete", key=f"delete_{app_id}"):
                    db.delete_application(app_id)
                    st.rerun()

with tab_analyzer:
    st.header("AI Job Analyzer")
    st.caption(
        "Keyword Matching runs locally with no external calls. "
        "The AI modes send the text to an external API and fall back to "
        "keyword matching if that's unavailable."
    )

    job_description = st.text_area(
        "Paste a job description here", height=250, key="jd_input"
    )

    if st.button("Analyze"):
        if not job_description.strip():
            st.warning("Paste a job description first.")
        elif not user_skills_text.strip():
            st.warning("List your skills in the sidebar first.")
        else:
            # Run the selected mode. AI modes internally fall back to
            # keyword matching on any failure, so this never crashes.
            if analysis_mode == "AI (Gemini)":
                result = analyzer.analyze_with_gemini(job_description, user_skills_text)
            elif analysis_mode == "AI (Groq)":
                result = analyzer.analyze_with_groq(job_description, user_skills_text)
            else:
                job_skills = analyzer.find_skills_in_description(job_description)
                keyword_result = analyzer.compare_skills(job_skills, user_skills_text)
                result = {
                    "mode": "keyword",
                    "match_score": keyword_result["match_score"],
                    "matched": keyword_result["matched"],
                    "missing": keyword_result["missing"],
                    "required_skills": job_skills,
                    "summary": None,
                }

            if not result["required_skills"]:
                st.info("No recognized tech skills were found in that job description.")
            else:
                # Show which mode actually produced this result (AI can fall back)
                mode_labels = {
                    "ai_gemini": "🤖 AI (Gemini)",
                    "ai_groq": "🤖 AI (Groq)",
                    "keyword": "🔤 Keyword Matching",
                    "keyword_fallback": "🔤 Keyword Matching (AI fallback)",
                }
                st.write(f"**Mode used:** {mode_labels.get(result['mode'], result['mode'])}")
                if result.get("fallback_reason"):
                    st.warning(result["fallback_reason"])

                # Big score number, clearly labeled as coverage, not a hiring prediction
                st.metric(
                    "Share of listed requirements you already cover",
                    f"{result['match_score']}%",
                )
                st.caption(
                    "This reflects skill overlap only — it is not a prediction "
                    "of your chances of getting hired."
                )

                if result.get("summary"):
                    st.write(f"**Summary:** {result['summary']}")

                col_missing, col_matched = st.columns(2)
                with col_missing:
                    st.subheader("Missing Skills")
                    if result["missing"]:
                        for skill in result["missing"]:
                            st.write(f"- {skill}")
                    else:
                        st.write("None — you cover every recognized skill!")

                with col_matched:
                    st.subheader("Matched Skills")
                    if result["matched"]:
                        for skill in result["matched"]:
                            st.write(f"- {skill}")
                    else:
                        st.write("No overlap found.")