-- Formal verification of the runtime evaluation pipeline.
-- Models the state machine for cldc's check/ci commands and proves
-- correctness properties of the evidence-evaluation stages.

/-- The states in the runtime evaluation pipeline -/
inductive EvaluationState where
  | Initial
  | EvidenceNormalized
  | RulesEvaluated
  | ViolationsDetected
  | Completed
  deriving DecidableEq, Repr

open EvaluationState

/-- Normalize incoming evidence (paths, claims, git writes) to canonical form. -/
def normalizeEvidence : EvaluationState → EvaluationState
  | Initial => EvidenceNormalized
  | s       => s

/-- Evaluate each policy rule against the normalized evidence set. -/
def evaluateRules : EvaluationState → EvaluationState
  | EvidenceNormalized => RulesEvaluated
  | s                  => s

/-- Collect and classify violations from rule evaluation results. -/
def detectViolations : EvaluationState → EvaluationState
  | RulesEvaluated => ViolationsDetected
  | s              => s

/-- Finalize the evaluation and produce a policy decision. -/
def completeEvaluation : EvaluationState → EvaluationState
  | ViolationsDetected => Completed
  | s                  => s

/-- Predicate: the evaluator has reached the terminal Completed state. -/
def reachesCompleted : EvaluationState → Prop
  | Completed => True
  | _         => False

-- ── Core correctness theorems ─────────────────────────────────────────────

/-- The full evaluation pipeline starting from Initial reaches Completed. -/
theorem evaluation_completes :
    reachesCompleted
      (completeEvaluation (detectViolations (evaluateRules (normalizeEvidence Initial)))) := by
  simp [normalizeEvidence, evaluateRules, detectViolations, completeEvaluation, reachesCompleted]

/-- Each stage transitions correctly from its expected predecessor state. -/
theorem correct_transitions :
    normalizeEvidence Initial       = EvidenceNormalized ∧
    evaluateRules EvidenceNormalized = RulesEvaluated    ∧
    detectViolations RulesEvaluated  = ViolationsDetected ∧
    completeEvaluation ViolationsDetected = Completed := by
  simp [normalizeEvidence, evaluateRules, detectViolations, completeEvaluation]

-- ── Pipeline ordering theorems ────────────────────────────────────────────

/-- reachesCompleted holds exactly when the state is Completed. -/
theorem completed_iff (s : EvaluationState) :
    reachesCompleted s ↔ s = Completed := by
  cases s <;> simp [reachesCompleted]

/-- Rules cannot be evaluated before evidence is normalized. -/
theorem eval_requires_normalization :
    evaluateRules Initial = Initial := by
  simp [evaluateRules]

/-- Violations cannot be detected before rules are evaluated. -/
theorem detect_requires_eval :
    detectViolations Initial = Initial := by
  simp [detectViolations]

/-- normalizeEvidence is idempotent once past Initial. -/
theorem normalizeEvidence_idempotent (s : EvaluationState) (h : s ≠ Initial) :
    normalizeEvidence (normalizeEvidence s) = normalizeEvidence s := by
  cases s <;> simp_all [normalizeEvidence]

-- ── Collection-size helpers ───────────────────────────────────────────────

/-- A non-empty violation list has positive length. -/
theorem nonempty_violations_positive {α : Type} (vs : List α) (h : vs ≠ []) :
    0 < vs.length := by
  match vs with
  | []      => exact absurd rfl h
  | _ :: _ => exact Nat.succ_pos _
