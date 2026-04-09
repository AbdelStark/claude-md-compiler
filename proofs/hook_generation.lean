-- Formal verification of the hook generation pipeline.
-- Models the state machine for cldc's hook artifact generation and
-- installation and proves correctness of the sequential hook stages.

/-- The states in the hook generation pipeline -/
inductive HookState where
  | Initial
  | ArtifactGenerated
  | ArtifactInstalled
  | Completed
  deriving DecidableEq, Repr

open HookState

/-- Generate the hook artifact (script content + target path). -/
def generateArtifact : HookState → HookState
  | Initial           => ArtifactGenerated
  | s                 => s

/-- Write the artifact to its installation target. -/
def installArtifact : HookState → HookState
  | ArtifactGenerated => ArtifactInstalled
  | s                 => s

/-- Mark the hook generation pipeline as complete. -/
def completeGeneration : HookState → HookState
  | ArtifactInstalled => Completed
  | s                 => s

/-- Predicate: the pipeline has reached the terminal Completed state. -/
def reachesCompleted : HookState → Prop
  | Completed => True
  | _         => False

-- ── Core correctness theorems ─────────────────────────────────────────────

/-- The full hook generation pipeline starting from Initial reaches Completed. -/
theorem hook_generation_completes :
    reachesCompleted (completeGeneration (installArtifact (generateArtifact Initial))) := by
  simp [generateArtifact, installArtifact, completeGeneration, reachesCompleted]

/-- Each stage transitions correctly from its expected predecessor state. -/
theorem correct_transitions :
    generateArtifact Initial          = ArtifactGenerated ∧
    installArtifact ArtifactGenerated = ArtifactInstalled ∧
    completeGeneration ArtifactInstalled = Completed := by
  simp [generateArtifact, installArtifact, completeGeneration]

-- ── Pipeline ordering theorems ────────────────────────────────────────────

/-- reachesCompleted holds exactly when the state is Completed. -/
theorem completed_iff (s : HookState) :
    reachesCompleted s ↔ s = Completed := by
  cases s <;> simp [reachesCompleted]

/-- Artifact cannot be installed before it is generated. -/
theorem install_requires_generation :
    installArtifact Initial = Initial := by
  simp [installArtifact]

/-- Generation cannot be completed before artifact is installed. -/
theorem complete_requires_install :
    completeGeneration Initial = Initial := by
  simp [completeGeneration]

/-- generateArtifact is idempotent once past Initial. -/
theorem generateArtifact_idempotent (s : HookState) (h : s ≠ Initial) :
    generateArtifact (generateArtifact s) = generateArtifact s := by
  cases s <;> simp_all [generateArtifact]

-- ── Hook kind enumeration ─────────────────────────────────────────────────

/-- The supported hook kinds -/
inductive HookKind where
  | GitPreCommit
  | ClaudeCode
  deriving DecidableEq, Repr

/-- Every hook kind is either GitPreCommit or ClaudeCode (exhaustive). -/
theorem hook_kinds_exhaustive (k : HookKind) :
    k = HookKind.GitPreCommit ∨ k = HookKind.ClaudeCode := by
  cases k
  · exact Or.inl rfl
  · exact Or.inr rfl

/-- There are exactly two distinct hook kinds. -/
theorem exactly_two_hook_kinds :
    HookKind.GitPreCommit ≠ HookKind.ClaudeCode := by
  decide
