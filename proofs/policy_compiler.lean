-- Formal verification of the policy compilation pipeline.
-- Models the state machine for cldc's compile command and proves
-- correctness properties of the sequential compilation stages.

/-- The states in the policy compilation pipeline -/
inductive CompilationState where
  | Initial
  | SourcesLoaded
  | RulesParsed
  | LockfileGenerated
  | Completed
  deriving DecidableEq, Repr

open CompilationState

/-- Load policy sources from the repository.
    Has no effect if not in Initial state (idempotent guard). -/
def loadSources : CompilationState → CompilationState
  | Initial => SourcesLoaded
  | s       => s

/-- Parse and validate policy rules from loaded sources. -/
def parseRules : CompilationState → CompilationState
  | SourcesLoaded => RulesParsed
  | s             => s

/-- Generate the deterministic policy lockfile from parsed rules. -/
def generateLockfile : CompilationState → CompilationState
  | RulesParsed => LockfileGenerated
  | s           => s

/-- Mark the compilation pipeline as complete. -/
def completeCompilation : CompilationState → CompilationState
  | LockfileGenerated => Completed
  | s                 => s

/-- Predicate: the pipeline has reached the terminal Completed state. -/
def reachesCompleted : CompilationState → Prop
  | Completed => True
  | _         => False

-- ── Core correctness theorems ─────────────────────────────────────────────

/-- The full compilation pipeline starting from Initial reaches Completed. -/
theorem compilation_completes :
    reachesCompleted (completeCompilation (generateLockfile (parseRules (loadSources Initial)))) := by
  simp [loadSources, parseRules, generateLockfile, completeCompilation, reachesCompleted]

/-- Each stage transitions correctly from its expected predecessor state. -/
theorem correct_transitions :
    loadSources Initial        = SourcesLoaded    ∧
    parseRules SourcesLoaded   = RulesParsed      ∧
    generateLockfile RulesParsed = LockfileGenerated ∧
    completeCompilation LockfileGenerated = Completed := by
  simp [loadSources, parseRules, generateLockfile, completeCompilation]

-- ── Pipeline ordering theorems ────────────────────────────────────────────

/-- reachesCompleted holds exactly when the state is Completed. -/
theorem completed_iff (s : CompilationState) :
    reachesCompleted s ↔ s = Completed := by
  cases s <;> simp [reachesCompleted]

/-- Rules cannot be parsed without first loading sources:
    parseRules is a no-op on Initial. -/
theorem parse_requires_sources :
    parseRules Initial = Initial := by
  simp [parseRules]

/-- Lockfile generation cannot start before rules are parsed:
    generateLockfile is a no-op on Initial. -/
theorem lockfile_requires_parsed :
    generateLockfile Initial = Initial := by
  simp [generateLockfile]

/-- Once in a non-Initial state, loadSources is idempotent. -/
theorem loadSources_idempotent (s : CompilationState) (h : s ≠ Initial) :
    loadSources (loadSources s) = loadSources s := by
  cases s <;> simp_all [loadSources]

-- ── Collection-size helpers ───────────────────────────────────────────────

/-- A non-empty rule list has positive length. -/
theorem nonempty_has_positive_length {α : Type} (xs : List α) (h : xs ≠ []) :
    0 < xs.length := by
  match xs with
  | []      => exact absurd rfl h
  | _ :: _ => exact Nat.succ_pos _
