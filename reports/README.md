# reports/

Result tables land here from milestone 4 (forecast and evaluation) onwards. Milestones 0 to 3
produce none, so this file is the only thing in the folder until then. Git does not keep empty
folders, so without it the folder would not exist in a clone.

Every table here is **produced by the pipeline** in `src/arima_forecasting/` and is **never
edited by hand**. To change a number, change the code or the data and re-run the pipeline. That
keeps each published number traceable to one function, one commit and one data snapshot (see
[ADR-0001](../docs/adr/0001-python-computes-app-visualises.md)).
