# TicketLab AI Office

Local visual console, adapted from Munizada/agent-office (MIT; see LICENSE).

Run `./start-office.ps1` in PowerShell, then open http://localhost:8766.
The existing read-only agent-service/dashboard.py must be running on port 8765.

- React / React Three Fiber / Three.js office, orbit and zoom controls.
- Five role desks, selected Story, real Redmine task progress and attachments.
- Click a role for its reported handoff and checks; click Tasks for products and journals.
- Polls /api/state every five seconds through the local Vite proxy.
- PM avatar represents the human user. The bottom form now POSTs a persistent command to the local controller. Role names route a real Codex specialist invocation; the selected recipient handles unnamed requests.
- Chat history is stored in runtime/state.sqlite per Story and role. The model receives the last eight completed exchanges for that role plus Story, plan, previous results, and the isolated checkout. Reloading preserves history. The UI polls every 2.5 seconds and shows queued/running/done/failed. Speech bubbles display real replies.
- Chat and workflow execute serially inside the same locked controller; only one agent invocation edits the worktrees at once. Questions preserve workflow state; chat does not automatically resume a failed stage. Validated completed_tasks still go through the product uploader. A BA-requested complete plan is validated before creating children.
- The local POST endpoint validates host/origin/content type/length, roles and known Story; request IDs deduplicate network retries. Interrupted running chats fail on restart rather than replaying an uncertain code mutation.
- Idle actors cycle through walking in their own aisle, reading a book and drinking tea. These illustrative animations never mutate job state, progress, or Redmine. Reduced-motion preferences disable walking and gestures.
- Existing background orchestration is unchanged: sequential BA, Backend, Frontend, Reviewer, QA. A 3D character is a view of that role, not a newly created worker.
- No automatic GitHub push or merge is added by this UI.

Validation: npm run build (TypeScript + Vite); browser checks of mobile and desktop layouts, agent handoff panel and task attachment list.

## Expanded office

28 x 22 floor, eight desks (five workers; three empty stations), library, coffee bar, four lounge seats, two foosball tables, training field, server cabinets and analytics display. Idle role labels appear only on pointer hover; running roles display unfinished tasks from the real Story plan (a role may handle several tasks per run). Chat bubbles expire after 25 seconds; chat history remains in the dock for the current session.

## Drag and drop activities

Idle actors can be dragged by holding the primary pointer on the character. Pointer capture keeps dragging responsive outside the original body. Camera orbit is disabled during the gesture and restored on release/cancel/unmount. Drop location selects soccer, reading, tea, resting, or standing; bounded floor coordinates prevent losing actors off the floor. Placement is browser-session state, resets on reload, and is cleared when real work begins. Working actors cannot be moved. This never changes Redmine job state.

Soccer pitch rebuilt with alternating turf, markings, penalty boxes, two netted goals and four floodlights. Work islands have cyan task lighting; tea/meeting/lounge have warmer and violet accents.

Verified: TypeScript/Vite build, seven zone/boundary checks, actual browser drag from office to soccer then library and lounge (reading/resting labels observed).

## Autonomous leisure

Idle workers now choose between soccer, reading, tea and resting, walk via the central aisle and select another activity after a pause. Dragging has been removed from the current UI. Real work overrides leisure and returns the actor to its desk. These are visualization activities, not independent decisions made by the LLM.


## Whole team and GitHub

CẢ ĐỘI routes commands to the deterministic controller. `Cả đội làm Story 44` starts/resumes the real pipeline; a progress question is read-only. The toolbar exposes Xem app for the isolated frontend and a PR/checks link once publishing succeeds. PM's speech includes the team dispatch acknowledgement. The five models still execute sequentially and communicate through persisted plans, reports and fix tasks.


## Parallel activity display

The dashboard exposes real running_roles and parallel_tasks from the controller. All concurrently running specialists return to their desks with role-specific labels. BA/QA/Reviewer labels explicitly identify support/preparation passes; final independent review and QA occur after dev code integration. Historical task statuses are not used to invent running activity.
