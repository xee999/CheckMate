"""Management Admin Console UI for CheckMate Web.

Renders restricted Admin control panel:
1. User Creation / Deletion / Role management
2. Safe Backend API key and LLM Model configuration
3. System Audit logs overview
"""

from __future__ import annotations

from nicegui import app, ui
import auth
import config_manager

# Preset popular LLM models for easy admin selection
PRESET_MODELS = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "opencode/deepseek-v4-flash-free",
    "gpt-4o",
    "gpt-4o-mini",
    "claude-3-5-sonnet",
    "custom",
]

PRESET_BASE_URLS = {
    "gemini-3.6-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "gemini-2.5-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "gemini-2.0-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "opencode/deepseek-v4-flash-free": "https://opencode.ai/zen/v1",
    "gpt-4o": "https://api.openai.com/v1",
    "gpt-4o-mini": "https://api.openai.com/v1",
}



def render_admin_console(user_session: dict, on_navigate_workspace) -> None:
    """Render the Admin Management Console."""
    if not user_session or user_session.get("role") != "admin":
        ui.notify("Access Denied. Admin privileges required.", type="negative")
        on_navigate_workspace()
        return

    # Container
    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        # Header banner
        with ui.row().classes("w-full items-center justify-between border-b pb-4"):
            with ui.row().classes("items-center gap-3"):
                ui.html('''<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#CCF458" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>''')
                ui.label("CheckMate — Management Admin Console").classes("text-2xl font-bold text-gray-900 dark:text-white")
            
            with ui.row().classes("items-center gap-3"):
                ui.button("Return to Workspace", icon="space_dashboard", on_click=on_navigate_workspace).props("flat color=primary")

        # Tabs navigation
        with ui.tabs().classes("w-full") as tabs:
            tab_llm = ui.tab("API & LLM Config", icon="key")
            tab_users = ui.tab("User Management", icon="people")
            tab_audits = ui.tab("System Audit Logs", icon="history")

        with ui.tab_panels(tabs, value=tab_llm).classes("w-full bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700"):
            
            # ── 1. API KEY & MODEL SELECTION ──────────────────────────
            with ui.tab_panel(tab_llm):
                ui.label("LLM Engine & API Credentials Setup").classes("text-lg font-semibold mb-2 text-gray-800 dark:text-gray-100")
                ui.label("Configure system-wide AI parameters. API Keys reside securely encrypted on backend database.").classes("text-sm text-gray-500 mb-6")

                config = config_manager.load_config()
                current_key = config.get("api_key", "")
                current_model = config.get("model", config_manager.DEFAULT_MODEL)
                current_url = config.get("base_url", config_manager.DEFAULT_BASE_URL)
                current_rpm = str(config.get("rpm_limit", "13"))

                # Masked Key preview
                masked_key = f"{current_key[:4]}...{current_key[-4:]}" if len(current_key) > 8 else ("Set" if current_key else "Not Set")

                with ui.column().classes("w-full max-w-2xl gap-4"):
                    # API Key field
                    api_key_input = ui.input(
                        label="API Key",
                        placeholder="sk-...",
                        value=current_key,
                        password=True,
                        password_toggle_button=True,
                    ).props("type=password password-toggle-button").classes("w-full")


                    # Model selection dropdown (Admin only)
                    model_select = ui.select(
                        options=PRESET_MODELS,
                        label="Active Global LLM Model",
                        value=current_model if current_model in PRESET_MODELS else "custom",
                    ).classes("w-full")

                    custom_model_input = ui.input(
                        label="Custom Model Identifier",
                        value=current_model if current_model not in PRESET_MODELS else "",
                    ).classes("w-full")
                    custom_model_input.bind_visibility_from(model_select, "value", backward=lambda v: v == "custom")

                    # Base URL field
                    base_url_input = ui.input(
                        label="Base API URL Endpoint",
                        value=current_url,
                    ).classes("w-full")

                    def auto_fill_url(e):
                        if e.value in PRESET_BASE_URLS:
                            base_url_input.value = PRESET_BASE_URLS[e.value]
                    model_select.on_value_change(auto_fill_url)

                    # RPM Limit field
                    rpm_input = ui.input(
                        label="Rate Limit (RPM - Requests Per Minute)",
                        value=current_rpm,
                    ).classes("w-full")

                    # Save config handler
                    def save_llm_settings():
                        selected_m = custom_model_input.value if model_select.value == "custom" else model_select.value
                        if not selected_m:
                            ui.notify("Please specify a valid model name.", type="warning")
                            return

                        config_manager.set("api_key", api_key_input.value.strip())
                        config_manager.set("model", selected_m.strip())
                        config_manager.set("base_url", base_url_input.value.strip())
                        config_manager.set("rpm_limit", rpm_input.value.strip())

                        ui.notify("LLM & API Credentials safely saved to encrypted backend store!", type="positive")

                    ui.button("Save API & Model Settings", icon="save", on_click=save_llm_settings).props("color=positive").classes("mt-2")

            # ── 2. USER MANAGEMENT ─────────────────────────────────────
            with ui.tab_panel(tab_users):
                with ui.row().classes("w-full justify-between items-center mb-4"):
                    with ui.column():
                        ui.label("Registered Accounts").classes("text-lg font-semibold text-gray-800 dark:text-gray-100")
                        ui.label("Provision, deactivate, or remove user access.").classes("text-sm text-gray-500")
                    
                    # Create User Dialog Trigger
                    def open_create_user_dialog():
                        with ui.dialog() as dialog, ui.card().classes("w-96 p-6"):
                            ui.label("Create New User Account").classes("text-lg font-bold mb-4")
                            new_uname = ui.input("Username").classes("w-full")
                            new_email = ui.input("Email").classes("w-full")
                            new_pwd = ui.input("Initial Password", password=True, password_toggle_button=True).classes("w-full")
                            new_role = ui.select(options=["user", "admin"], label="Role", value="user").classes("w-full")

                            def submit_user():
                                if not new_uname.value or not new_email.value or not new_pwd.value:
                                    ui.notify("All fields are required.", type="warning")
                                    return
                                try:
                                    auth.create_user(new_uname.value, new_email.value, new_pwd.value, new_role.value)
                                    ui.notify(f"User '{new_uname.value}' created successfully!", type="positive")
                                    dialog.close()
                                    refresh_users_table()
                                except ValueError as err:
                                    ui.notify(str(err), type="negative")

                            with ui.row().classes("w-full justify-end mt-4 gap-2"):
                                ui.button("Cancel", on_click=dialog.close).props("flat")
                                ui.button("Create Account", on_click=submit_user).props("color=primary")

                        dialog.open()

                    ui.button("Create User", icon="person_add", on_click=open_create_user_dialog).props("color=primary")

                # User Table Container
                user_table_container = ui.column().classes("w-full")

                def refresh_users_table():
                    user_table_container.clear()
                    users_list = auth.list_users()
                    
                    columns = [
                        {"name": "id", "label": "ID", "field": "id", "required": True},
                        {"name": "username", "label": "Username", "field": "username", "sortable": True},
                        {"name": "email", "label": "Email", "field": "email"},
                        {"name": "role", "label": "Role", "field": "role", "sortable": True},
                        {"name": "created_at", "label": "Created At", "field": "created_at"},
                        {"name": "actions", "label": "Actions", "field": "actions"},
                    ]
                    
                    rows = []
                    for u in users_list:
                        rows.append({
                            "id": u["id"],
                            "username": u["username"],
                            "email": u["email"],
                            "role": u["role"].upper(),
                            "created_at": u["created_at"][:19].replace("T", " "),
                        })

                    with user_table_container:
                        table = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")
                        
                        # Custom actions column slot
                        table.add_slot('body-cell-actions', '''
                            <q-td :props="props">
                                <q-btn size="sm" color="negative" flat icon="delete" @click="$parent.$emit('delete', props.row)" />
                            </q-td>
                        ''')

                        def on_delete(e):
                            target_id = e.args.get("id")
                            target_uname = e.args.get("username")
                            if target_id == user_session.get("id"):
                                ui.notify("Cannot delete your own active admin account!", type="warning")
                                return
                            
                            auth.delete_user(target_id)
                            ui.notify(f"User '{target_uname}' deleted.", type="info")
                            refresh_users_table()

                        table.on('delete', on_delete)

                refresh_users_table()

            # ── 3. SYSTEM AUDIT LOGS ───────────────────────────────────
            with ui.tab_panel(tab_audits):
                ui.label("Global Audit Execution History").classes("text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2")
                ui.label("Track recent compliance audits submitted across all tenant users.").classes("text-sm text-gray-500 mb-4")

                runs = auth.list_audit_runs()
                if not runs:
                    ui.label("No audit runs recorded yet.").classes("text-gray-400 italic")
                else:
                    audit_cols = [
                        {"name": "id", "label": "Run ID", "field": "id"},
                        {"name": "username", "label": "User", "field": "username"},
                        {"name": "rfp_filename", "label": "RFP Document", "field": "rfp_filename"},
                        {"name": "status", "label": "Status", "field": "status"},
                        {"name": "score", "label": "Score %", "field": "score"},
                        {"name": "created_at", "label": "Timestamp", "field": "created_at"},
                    ]
                    audit_rows = [
                        {
                            "id": r["id"],
                            "username": r["username"],
                            "rfp_filename": r["rfp_filename"],
                            "status": r["status"].upper(),
                            "score": f"{r['score']:.1f}%",
                            "created_at": r["created_at"][:19].replace("T", " "),
                        }
                        for r in runs
                    ]
                    ui.table(columns=audit_cols, rows=audit_rows, row_key="id").classes("w-full")
