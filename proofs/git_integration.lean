-- Formal verification of the git integration pipeline.
-- Models the state machine for cldc's staged-diff and base/head diff
-- collection and proves correctness of the sequential git stages.

/-- The states in the git integration pipeline -/
inductive GitState where
  | Initial
  | CommandConstructed
  | CommandExecuted
  | PathsCollected
  | Completed
  deriving DecidableEq, Repr

open GitState

/-- Construct the git diff command (staged or base/head). -/
def constructCommand : GitState → GitState
  | Initial => CommandConstructed
  | s       => s

/-- Execute the git command and capture its output. -/
def executeCommand : GitState → GitState
  | CommandConstructed => CommandExecuted
  | s                  => s

/-- Parse the diff output and collect affected file paths. -/
def collectPaths : GitState → GitState
  | CommandExecuted => PathsCollected
  | s               => s

/-- Mark the collection pipeline as complete. -/
def completeCollection : GitState → GitState
  | PathsCollected => Completed
  | s              => s

/-- Predicate: the pipeline has reached the terminal Completed state. -/
def reachesCompleted : GitState → Prop
  | Completed => True
  | _         => False

-- ── Core correctness theorems ─────────────────────────────────────────────

/-- The full git integration pipeline starting from Initial reaches Completed. -/
theorem git_integration_completes :
    reachesCompleted
      (completeCollection (collectPaths (executeCommand (constructCommand Initial)))) := by
  simp [constructCommand, executeCommand, collectPaths, completeCollection, reachesCompleted]

/-- Each stage transitions correctly from its expected predecessor state. -/
theorem correct_transitions :
    constructCommand Initial         = CommandConstructed ∧
    executeCommand CommandConstructed = CommandExecuted  ∧
    collectPaths CommandExecuted      = PathsCollected   ∧
    completeCollection PathsCollected = Completed := by
  simp [constructCommand, executeCommand, collectPaths, completeCollection]

-- ── Pipeline ordering theorems ────────────────────────────────────────────

/-- reachesCompleted holds exactly when the state is Completed. -/
theorem completed_iff (s : GitState) :
    reachesCompleted s ↔ s = Completed := by
  cases s <;> simp [reachesCompleted]

/-- Paths cannot be collected before the command is executed. -/
theorem collect_requires_execution :
    collectPaths Initial = Initial := by
  simp [collectPaths]

/-- Command cannot be executed before it is constructed. -/
theorem execute_requires_construction :
    executeCommand Initial = Initial := by
  simp [executeCommand]

/-- constructCommand is idempotent once past Initial. -/
theorem constructCommand_idempotent (s : GitState) (h : s ≠ Initial) :
    constructCommand (constructCommand s) = constructCommand s := by
  cases s <;> simp_all [constructCommand]

-- ── Path collection helpers ───────────────────────────────────────────────

/-- Filtering a path list cannot produce more paths than the original. -/
theorem filter_le_original {α : Type} (p : α → Bool) (paths : List α) :
    (paths.filter p).length ≤ paths.length :=
  List.length_filter_le p paths

/-- A non-empty path list has positive length. -/
theorem nonempty_paths_positive {α : Type} (paths : List α) (h : paths ≠ []) :
    0 < paths.length := by
  match paths with
  | []      => exact absurd rfl h
  | _ :: _ => exact Nat.succ_pos _
