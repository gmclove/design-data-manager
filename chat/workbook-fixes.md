# Workbook Fixes (Applied 2026-11-03)

Problems found importing `2025.09.22_REVIT Schedules_Masters_Macro.xlsm`, with the fix applied
for each. "Heading" is the column heading on the schedule sheet.

## 1. Stray `IPS_SPACE_AirReq_Recirc` columns

`IPS_SPACE_AirReq_Recirc` (Yes/No) belongs only on `_SPACES - Air Balance` (RECIRC. AIRFLOW?). On 16
other sheets it has replaced the real parameter, apparently a lookup that slipped. Each one gets
the parameter that usually carries its heading.

| Schedule | Heading | Fix |
| --- | --- | --- |
| Pump | MANUF. | `IPS_EQUIP_BOD_Manuf` |
| VAV Unit | EQUIP. SERVED | `IPS_EQUIP_EquipAssoc_SysOrService` |
| Air Term | AREA SERVED | `IPS_EQUIP_Area_Served` (`IPS_TAG_AreaServed` is already a column) |
| Air Valve Schedule | MAX AIRFLOW (CFM) | `IPS_EQUIP_Airflow_Max_CFM` |
| Air Curtain | LENGTH (IN.) | `IPS_EQUIP_Max_Length` |
| Air Device | MATERIAL | `IPS_EQUIP_Material_TYPE` |
| Water Treatment | WATER FLOW (GPM) | `IPS_EQUIP_Water_Design_GPM` (no exact heading match; Pump's FLOW (GPM)) |
| _CTRL | NOTES | `IPS_CTRL_06_Notes` (follows `IPS_CTRL_05_Description`) |
| _TAG, Valves | Tag Term 3 - Middle | `IPS_TAG_TERM_3_Middle` |
| _Arch - Level, _Array | Element Name | `IPS_NAME` |
| _Arch - Levels | Mechanical Waterside Connection? | `IPS_GROUP_Mech_Waterside` |
| _Arch - Rooms, _Line - Pipe - Water, _Line - Pipe - Steam | (none) | Remove the column |

## 2. Schedule columns whose parameter doesn't exist

| Schedule | Column | Heading | Fix |
| --- | --- | --- | --- |
| Chiller (Water-Cooled), Chiller (Air-Cooled), Heat Pump (Air-Water) | `IPS_EQUIP_Evap_GPM` | EVAP. (DESIGN) FLOW (GPM) | `IPS_EQUIP_Evap_Design_GPM` |
| Hydronic Snow Melt Flr Manifold | `IPS_COIL_Htg_Total_MBH_per_SF` | UNIT CAPACITY (MBH/FT2) | `IPS_COIL_Htg_MBH_per_SF` |
| Radiator (Fin Tube) (HHW), Radiant Panel (HHW-CHW) | `IPS_COIL_Htg_Total_MBH_per_FT` | (MBH/FT) | `IPS_COIL_Htg_MBH_per_FT` |
| Steam Trap | `IPS_EQUIP_CapacityDesign_PPH` | DESIGN CAPACITY (LB/HR) | `IPS_EQUIP_Capacity_Design_PPH` |
| Steam Pressure Relief Valve | `IPS_EQUIP_Capacity_PPH` | CAPACITY (LB/HR) | `IPS_EQUIP_Capacity_Max_PPH` (relieving capacity) |
| _CTRL | `IPS_CTRL_11_PilotLightColor` | PILOT LIGHT COLOR | `IPS_CTRL_07_PilotLightColor` |
| _CTRL | `IPS_CTRL_Signal_Analog` | | `IPS_CTRL_01_Analog_YN` |
| _CTRL | `IPS_CTRL_Signal_Input` | | `IPS_CTRL_01_Input_YN` |
| _CTRL | `IPS_CTRL_12_DetailVarient` | DETAIL VARIENT | New parameter `IPS_CTRL_08_DetailVariant` (Text, Identity Data) |
| Heat Pump (Water-Water) | `IPS_COIL_LoadSide_Water_GPM` | COOLING FLOW (GPM) | New parameter `IPS_COIL_Clg_LoadSide_GPM` (Number, Mechanical - Flow), the cooling twin of `IPS_COIL_Htg_LoadSide_GPM` |
| _Line - Duct | (blank) | DUCT DIA. (IN.) | New parameter `IPS_DUCT_Dia_IN` (Text, Dimensions, like `IPS_DUCT_Width_IN`) |
| _Line - Duct, _Line - Pipe - Water, _Line - Pipe - Steam, Valves | `Name`, `NAME` | | Leftover export header columns; stay out |
| Air Device | `Column1` | TAG | Leftover; stays out |

## 3. Formulas

- `IPS_SPACE_AirReq_Transf_Net_CFM` sums `IPS_ROOM_Transfer_01_CFM` … `_15_CFM`, which don't exist.
  The parameters are named `IPS_SPACE_Transfer_01_CFM` … `_15_CFM`. Fix: rename them in the
  formula.
- 14 parameters have different Static and Dynamic formulas. The Dynamic ones are broken (`#REF!`,
  references to unrelated valve and tank parameters), so the Static ones are kept. No change
  needed.
- 14 "errors" for length values like `0' 0 1/16"` and the built-in `Length` were a bug in the app's
  formula checker. That is fixed.

## 4. Families

- `IPS-US_CTRL` appears 5 times: identical Multi-Category Tags rows with no type, description or
  view, so the name never completed. Fix: remove it (an unfinished placeholder).
