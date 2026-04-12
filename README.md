# Wize JMES Adapter

A configuration-driven orchestration engine to:

- Call APIs (REST)
- Transform data (JMESPath)
- Chain workflows
- Run parallel operations
- Apply business logic (risk, scoring, decisions)
- Build UI-ready responses

All **without writing vendor-specific Python code**.

---

# 🚀 1. What this library solves

Instead of writing custom code for every API integration, you define everything in YAML:

- API calls
- Request payloads
- Response mapping
- Workflow orchestration
- Business logic (risk, scoring, decisions)

---

# 🧠 2. Core Concepts

### Operation
Smallest unit of execution

Types:
- `REST` → API call
- `TRANSFORM` → derive data locally
- `workflow` → multi-step execution

---

### Context
Runtime input

```json
{
  "applicant_id": "A123",
  "tenant_id": "123"
}
Context Map

Maps data into child step

context_map:
  pan: results.customer_data[0].pan

Workflow
Sequence of steps

workflow:
  steps:
    - name: customer
      operation: customer_data

    - parallel_group:
        - name: experian
          operation: experian_branch
        - name: equifax
          operation: equifax_branch

⚙️ 3. Execution Flow
Load YAML
Identify operation
Execute steps (sequential / parallel)
Resolve context
Call API / transform
Apply response mapping
Return final output

🔌 4. Operation Types
  4.1 REST
  operation:
    type: REST
    details:
      route: "https://api.com"
      method: POST
      headers:
        required:
          Content-Type: application/json
      data:
        id: "${id}"

  response:
    expression: "@"
  4.2 TRANSFORM
  operation:
    type: TRANSFORM
    source: "results"

  response:
    expression: >
      {
        pan: customer_data[0].pan,
        income: employment_data[0].income
      }
  4.3 WORKFLOW
  workflow:
    steps:
      - name: step1
        operation: op1

      - parallel_group:
          - name: a
            operation: op_a
          - name: b
            operation: op_b

  response:
    expression: >
      {
        a: a[0],
        b: b[0]
      }

🔄 5. Result Behavior

All outputs are normalized:

  Input	Output
  dict	[dict]
  list	list
  None	[]

🔐 6. Authentication
auth:
  enabled: true
  operation: login_api
  context_map:
    username: context.username
    password: context.password
  result_map:
    token: "[0].token"

⚡ 7. Parallel Execution
- parallel_group:
    - name: experian
      operation: experian_branch
    - name: equifax
      operation: equifax_branch

🧩 8. YAML Functions
  Conditional
  functions:
    risk_band:
      type: conditional
      params: [score]
      rules:
        - when: "score >= 750"
          value: "LOW"
        - when: "score >= 650"
          value: "MEDIUM"
        - when: "true"
          value: "HIGH"
  Formula
  functions:
    confidence:
      type: formula
      params: [score]
      expression: "min(score / 900, 1)"
  Mapping
  functions:
    decision_label:
      type: mapping
      params: [value]
      map:
        1: "APPROVED"
        0: "REJECTED"

🧠 9. Using Functions
    risk: "risk_band(results.score[0])"
    confidence: "confidence(results.score[0])"

🎯 10. Template-Based Output
response:
  template:
    applicant:
      pan: "results.customer[0].pan"

    scores:
      experian: "results.experian[0].score"

    risk:
      experian: "risk_band(results.experian[0].score)"

🔍 11. Expression Types
      Type	Example
      context	context.applicant_id
      results	results.customer[0].pan
      item	item.id
      template	${auth_token}
      function	risk_band(score)
🐞 12. Debug Mode

  await adapter.run("workflow_name", context=context, debug=True)

🛡️ 13. Validation

    Validates:

      operations
      workflows
      functions
      auth

🏦 14. Example Flow
      fetch data
      transform payload
      call APIs (parallel)
      compute decision


▶️ 15. How to Use
    Initialize
      from wize_jmes_adapter import Adapter

      adapter = Adapter("config.yaml")

    Run
      result = await adapter.run(
          "banking_underwriting_workflow",
          context={"applicant_id": "A123"}
      )

    Debug
      await adapter.run("workflow", context=context, debug=True)

✅ 16. Best Practices
      Keep operations small
      Use TRANSFORM for payloads
      Use YAML for logic
      Avoid API-layer processing
      Keep response UI-ready

❌ 17. Common Mistakes
      Mixing raw + processed data
      Overloading context
      Using parallel for dependent steps
      Writing logic in Python instead of YAML

🎯 Final Summary

    This is not just an adapter.

    It is a:

      Workflow Engine
      Transformation Engine
      Decision Engine
      Low-code Integration Framework

    All powered by YAML.