# Build order

Hacking starts 11:00, demos 16:30, lunch 13:30. Treat this as a proposed
schedule, not a guarantee of training time. Training is the critical path.

## Before the event

Confirm the rules on pre-existing code. Registration approval and GPU credits
are not assumed.

Run `make verify`. It re-checks every line of `config/site.yaml` against the
live deployment and fails loudly if a channel, an appliance mapping, or a table
has moved.

Run `make adapter` as soon as an adapter exists. See
[VENDOR_SETUP.md](VENDOR_SETUP.md) for why a silently ignored adapter is the
single most likely way to end the day reporting a result that never happened.

Run `make replay` to freeze six hours of snapshots to disk. This is the demo
backup and it must exist before the day starts.

Inspect the label situation. Expect the anomaly table to be empty, so the first
dataset has to come from a rules replay over the historical archive. Count what
comes out by category and panel before deciding which categories to claim.

## During the event

11:00 to 11:40. Validate the replay set, the input and output contracts, and
one untuned request end to end. Measure training throughput on a smoke run
before committing to a schedule.

11:40 to 13:00. Launch the bounded fine-tune. Build the coordinator wiring and
the dashboard integration while it runs.

13:00 to 13:30. Validate an adapter checkpoint, save and reload it, register
the endpoint with Respan.

13:30 to 14:00. Lunch and buffer. Nothing critical may depend on unattended
training finishing here.

14:00 to 14:45. Evaluate the saved adapter against the untouched test inputs.
Complete the Nango review round trip with one real correction.

14:45 to 15:30. Integrate household coordination. Test one normal replay, one
anomaly replay, and one missing-data replay.

15:30 to 16:00. Freeze the evaluated model. Record measured results only.

16:00 to 16:30. Rehearse against the local replay backup, not the live house.

## Division of work

Four people: data and labels plus baseline evaluation, Gemma training and
serving, coordinator and dashboard, Nango and Respan integration plus demo
verification.

With fewer people, cut in this order: email notifications, then the three
separate per-panel adapters, then the coordinator's follow-up round.

## If training does not finish

Reduce examples or model size based on validation, use an allowed prepared
checkpoint, or demonstrate the prompted baseline and say so. An unfinished or
unused training job is never described as a fine-tuned deployment.

## Minimum useful demonstration

One complete incident workflow with three panel views, at least one evaluated
anomaly category, a fine-tuned adapter, an untuned baseline on the same inputs,
and one recorded human correction. Coverage may differ by panel. Unsupported
categories are marked unevaluated in `config/categories.yaml`, not omitted.

## Acceptance criteria

Three panel agents consume synchronized evidence and report explicit failures
or missing information.

At least one anomaly category is evaluated on reviewed held-out events and on
reviewed normal monitored time.

Rules-only, untuned, and tuned results use the same data and the same incident
matching definitions.

The original BiLSTM appliance inference is untouched.

A user can trace an incident to measurements and tell them apart from model
estimates.

A review correction completes the round trip without duplicating the incident.

Respan traces identify the exact model, adapter, prompt, and snapshot.

Measured latency fits the assessment cadence without a growing queue.

Demo labels distinguish real, replayed, and synthetic incidents.
