# Karmalite patient workflow

Phase 1 replaces the active Customer directory label with Patients while continuing to use the
tenant-owned `Customer` aggregate. This is a presentation and workflow change, not a second patient
identity store.

## Directory and profile

- `/{locale}/customers` is the permission-scoped, paginated patient directory.
- Search accepts name, patient reference, and partial telephone number. Results contain only the
  patient identifier, display name, reference, and contact fields that the viewer may read.
- `/{locale}/customers/{patientId}` provides Overview, Appointments, Doctor Notes, Health &
  Allergies, Communications, and Audit tabs. Unauthorized tabs are absent and their repository
  methods still reject direct calls.
- Appointments are split into Upcoming (ascending) and Previous (newest first) and link to the
  shared appointment details drawer.

## Creating a patient while booking

The appointment wizard supports finding an existing patient or creating a new one with name,
telephone, optional email, and preferred language. Telephone values are normalized and duplicate
telephone numbers are rejected with a safe conflict instead of silently merging or overwriting a
record.

Safety intake fields are shown only to an actor with `patients.health.write`. A user without that
permission can create a patient with health states left as `NOT_PROVIDED`, but cannot submit hidden
health data.

## Protected safety intake

The only supported sensitive intake fields are allergies and known diseases or medical conditions.
Each uses one explicit state: `NOT_PROVIDED`, `NONE_REPORTED`, `PROVIDED`, or `DECLINED`. `PROVIDED`
requires text; every other state forbids text. Any recorded patient response other than
`NOT_PROVIDED` requires confirmed patient authorization and a linked consent/provenance record.

This data exists only to support safe intake and appointment handling. It is not an EMR. Diagnosis,
prescriptions, medication management, insurance, clinical plans, surgical records, and broad medical
history are intentionally absent.
