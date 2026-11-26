- Fine tune the part where the factory decides to not merge and wait for a human CR - so far 3/3 PRs did not ask for a CR. We need to find the threshold and see if we like it
- Implement workflow for CR ping pong with human: 
	- Approver escalated to human CR
	- Human reviewer requested changes and made comments to the PR
	- The request for changes triggers an agent similar to the spec writer that would update the spec or simply extend it following the comments
- Large task flow that would split into smaller tasks after writing the spec
	- potentially recursive i.e. subtasks would be divided to smaller subtasks
	- Should the intake reject with the reason that the task is too big and we should consider submitting it to the large task flow? If so how should we get the answer of the user
- Flow.issue_driven is too github specific
- Detect the PR has conflicts and resolve them
- Stage enum per workflow kind


## Next tasks in line
- [[Choose a CLI library]]
- Clear incompatible history in postgres:
  @workflow.defn(name="JobWorkflow")  # historical type name: in-flight runs and the queue use it
- Reduce optional values type hints