"""
FlowPilot CLI Interface
Interactive CLI tool for testing and demonstrating FlowPilot autonomous workflows.
Supports both interactive prompts and command-line flags.
Windows-safe unicode handling.
"""

import sys
import json
import argparse

# Ensure safe output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.database import get_db_connection, DB_PATH
from agent.graph import run_leave_workflow, resume_workflow


def print_separator(title: str = ""):
    print("\n" + "=" * 25 + f" {title} " + "=" * 25)


def show_audit_logs(request_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT step_name, actor, action, details, timestamp FROM audit_log WHERE request_id = ? ORDER BY id ASC",
        (request_id,)
    )
    logs = cursor.fetchall()
    conn.close()

    print("\n[AUDIT LOG TRAIL]")
    for log in logs:
        print(f"[{log['timestamp']}] [{log['actor']}] {log['step_name']} -> {log['action']}")
        if log['details']:
            print(f"   Details: {log['details']}")


def show_notifications(employee_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, message, created_at FROM notifications WHERE employee_id = ? ORDER BY id DESC LIMIT 3",
        (employee_id,)
    )
    notifs = cursor.fetchall()
    conn.close()

    print("\n[EMPLOYEE NOTIFICATIONS]")
    for n in notifs:
        print(f"[{n['created_at']}] (Notif #{n['id']}): {n['message']}")


def main():
    parser = argparse.ArgumentParser(description="FlowPilot Autonomous Workflow CLI")
    parser.add_argument("--employee", default="EMP001", help="Employee ID (default: EMP001)")
    parser.add_argument("--request", help="Plain English request string")
    parser.add_argument("--action", choices=["approve", "reject", "pause"], help="Automatic approver action")
    parser.add_argument("--comment", default="Approved by manager", help="Approver comment")
    args = parser.parse_args()

    print_separator("FLOWPILOT AUTONOMOUS WORKFLOW AGENT")
    print("Welcome to FlowPilot CLI!")
    print("Test multi-step workflows with AI classification and human-in-the-loop approvals.\n")

    employee_id = args.employee
    default_prompt = "I need 2 days annual leave from Nov 5 for a family vacation."

    if args.request:
        user_input = args.request
    else:
        print(f"Active Employee: {employee_id} (Alice Smith - Engineering)")
        print(f"Default request: \"{default_prompt}\"")
        try:
            user_input = input("\nEnter your request (press Enter for default): ").strip()
        except EOFError:
            user_input = default_prompt
        if not user_input:
            user_input = default_prompt

    print_separator("STEP 1 & 2: AGENT CLASSIFICATION & APPROVAL PAUSE")
    print(f"Submitting: '{user_input}'...")
    state = run_leave_workflow(raw_text=user_input, employee_id=employee_id)

    req_id = state["request_id"]
    print(f"\n[OK] Request Created: {req_id}")
    print(f"   Workflow Type:   {state['workflow_type']}")
    print(f"   Extracted Data:  {json.dumps(state['extracted_data'])}")
    print(f"   Current Status:  {state['status']}")
    print(f"   Current Step:    {state['current_step']}")

    show_audit_logs(req_id)

    if state["status"] == "pending_approval":
        print_separator("HUMAN-IN-THE-LOOP APPROVAL DASHBOARD")
        print(f"The workflow is currently PAUSED waiting for Manager approval on {req_id}.")

        if args.action:
            choice = "A" if args.action == "approve" else ("R" if args.action == "reject" else "Q")
            comment = args.comment
        else:
            try:
                choice = input("\nAction as Manager: [A]pprove / [R]eject / [Q]uit? (default: A): ").strip().upper()
            except EOFError:
                choice = "A"
            if choice == "R":
                try:
                    comment = input("Enter rejection reason (default: Project deadline): ").strip() or "Project deadline"
                except EOFError:
                    comment = "Project deadline"
            else:
                try:
                    comment = input("Enter approval comment (default: Approved, enjoy!): ").strip() or "Approved, enjoy!"
                except EOFError:
                    comment = "Approved, enjoy!"

        if choice == "R":
            print(f"\nResuming workflow with REJECTION ({comment})...")
            final_state = resume_workflow(request_id=req_id, decision="REJECTED", comments=comment)
        elif choice == "Q":
            print("\nExiting. Workflow remains pending in database.")
            return
        else:
            print(f"\nResuming workflow with APPROVAL ({comment})...")
            final_state = resume_workflow(request_id=req_id, decision="APPROVED", comments=comment)

        print_separator("FINAL WORKFLOW STATE")
        print(f"Status:       {final_state['status']}")
        print(f"Current Step: {final_state['current_step']}")
        if final_state.get("error_message"):
            print(f"Error:        {final_state['error_message']}")

        show_audit_logs(req_id)
        show_notifications(employee_id)

    print_separator("PHASE 2 CLI DEMO COMPLETE")


if __name__ == "__main__":
    main()
