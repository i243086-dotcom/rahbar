# Real-corpus UI demo

The supplied screenshots show RAHBAR at `localhost:8000` with Ollama listed as the provider. The address alone does not establish that these requests went through Kubernetes Ingress.

| Screenshot | Observed behavior |
| --- | --- |
| [Academic warning](real-corpus-academic-warning.jpg) | The app answers below 2.00 CGPA and cites the June 2026 Academic Rules Handbook, section 5.4, page 24. |
| [Attendance](real-corpus-attendance.jpg) | The app answers the question about clause 1.21 and cites pages 10 and 11 of the June 2026 handbook. |
| [2023 graduation rules](real-corpus-2023-graduation.jpg) | The app answers the year-specific question and cites the August 2023 undergraduate academic rules, page 8. |
| [Hostel rules](real-corpus-hostel-abstention.jpg) | The app declines to guess about visitor rules and curfew. |
| [Instruction override attempt](real-corpus-instruction-override.jpg) | The app declines the prompt's request to claim that attendance is optional. |
