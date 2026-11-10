# Golden example suite — plan

**137 examples across 48 templates and 7 sports.** Every era of every viewpoint each template places appears in at least one example, drawn from real elements.

Review this, edit `golden/manifest.yaml` (set `approved: false` to skip an example, or change any element), then run:

    python3 scripts/golden/golden_run.py

How examples are chosen: greedily, so each one covers as many uncovered eras as possible; within a team, elements from the same year are preferred so a combination looks like one actually worn; elements with numbered files are preferred so number resolution is exercised. Explicit placements (the football helmet-left inset) get one extra example each.

## Baseball

### `diamond-jersey` — 1 example
_Constraint: uniform 1: no tq jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 Black **18** | jersey back **std**, jersey front **std** |

### `diamond-jersey-tq` — 1 example
_Constraint: uniform 1: jersey tq only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2015 Natural Wool **48** | jersey back **tq**, jersey front **tq** |

### `baseball-full` — 3 examples
_Constraint: uniform 1: no tq jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | hat: 1959 White<br>jersey: 1959 White **59**<br>pants: 1959 White | hat front **classic**, jersey back **std**, jersey front **std**, pants left **std** |
| 2 | Mississippi State | hat: 2026 Gray<br>jersey: 2026 Gray **7**<br>pants: 2026 Gray | hat front **modern**, jersey back **std**, jersey front **std**, pants left **std** |
| 3 | Mississippi State | hat: 1976 Maroon<br>jersey: 1975 White **1**<br>pants: 1975 White | hat front **classic**, jersey back **std**, jersey front **std**, pants left **blt** |

### `baseball-full-tq` — 3 examples
_Constraint: uniform 1: jersey tq only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | hat: 1923 Natural<br>jersey: 1923 Natural **23**<br>pants: 1923 Natural | hat front **classic**, jersey back **tq**, jersey front **tq**, pants left **std** |
| 2 | Mississippi State | hat: 2015 Maroon Fauxback<br>jersey: 2015 Natural Wool **48**<br>pants: 2015 Natural Wool | hat front **modern**, jersey back **tq**, jersey front **tq**, pants left **std** |
| 3 | Mississippi State | hat: 2015 Maroon Fauxback<br>jersey: 2015 Natural Wool **48**<br>pants: 1977 Gray | hat front **modern**, jersey back **tq**, jersey front **tq**, pants left **blt** |

### `baseball-condensed` — 3 examples
_Constraint: uniform 1: no tq jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | hat: 1959 White<br>jersey: 1959 White **59**<br>pants: 1959 White | hat front **classic**, jersey front **std**, pants left **std** |
| 2 | Mississippi State | hat: 2026 Gray<br>jersey: 2026 Gray **7**<br>pants: 2026 Gray | hat front **modern**, jersey front **std**, pants left **std** |
| 3 | Mississippi State | hat: 1976 Maroon<br>jersey: 1975 White **1**<br>pants: 1975 White | hat front **classic**, jersey front **std**, pants left **blt** |

### `baseball-condensed-tq` — 3 examples
_Constraint: uniform 1: jersey tq only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | hat: 1923 Natural<br>jersey: 1923 Natural **23**<br>pants: 1923 Natural | hat front **classic**, jersey front **tq**, pants left **std** |
| 2 | Mississippi State | hat: 2015 Maroon Fauxback<br>jersey: 2015 Natural Wool **48**<br>pants: 2015 Natural Wool | hat front **modern**, jersey front **tq**, pants left **std** |
| 3 | Mississippi State | hat: 2015 Maroon Fauxback<br>jersey: 2015 Natural Wool **48**<br>pants: 1977 Gray | hat front **modern**, jersey front **tq**, pants left **blt** |

### `baseball-tall` — 3 examples
_Constraint: uniform 1: no tq jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | hat: 1959 White<br>jersey: 1959 White **59**<br>pants: 1959 White | hat front **classic**, jersey front **std**, pants left **std** |
| 2 | Mississippi State | hat: 2026 Gray<br>jersey: 2026 Gray **7**<br>pants: 2026 Gray | hat front **modern**, jersey front **std**, pants left **std** |
| 3 | Mississippi State | hat: 1976 Maroon<br>jersey: 1975 White **1**<br>pants: 1975 White | hat front **classic**, jersey front **std**, pants left **blt** |

### `baseball-tall-tq` — 3 examples
_Constraint: uniform 1: jersey tq only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | hat: 1923 Natural<br>jersey: 1923 Natural **23**<br>pants: 1923 Natural | hat front **classic**, jersey front **tq**, pants left **std** |
| 2 | Mississippi State | hat: 2015 Maroon Fauxback<br>jersey: 2015 Natural Wool **48**<br>pants: 2015 Natural Wool | hat front **modern**, jersey front **tq**, pants left **std** |
| 3 | Mississippi State | hat: 2015 Maroon Fauxback<br>jersey: 2015 Natural Wool **48**<br>pants: 1977 Gray | hat front **modern**, jersey front **tq**, pants left **blt** |


## Football

### `full` — 12 examples + 1 explicit
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | helmet: 1939 Maroon<br>jersey: 1939 Maroon **4**<br>pants: 1939 Maroon | helmet back **A**, helmet front **A**, helmet right **A**, jersey back **A**, jersey front **A**, pants front **all**, pants left **all** |
| 2 | Mississippi State | helmet: 2004 White<br>jersey: 2004 White **12**<br>pants: 2004 White | helmet back **BCD**, helmet front **D**, helmet right **D**, jersey back **C**, jersey front **C**, jersey left **all**, pants front **all**, pants left **all** |
| 3 | Mississippi State | helmet: 2012 Maroon<br>jersey: 2012 Maroon **15**<br>pants: 2012 Maroon | helmet back **E**, helmet front **E**, helmet right **E**, jersey back **D**, jersey front **D**, jersey left **all**, pants front **all**, pants left **all** |
| 4 | Mississippi State | helmet: 2011 Maroon Egg Bowl<br>jersey: 2011 Maroon Egg Bowl **14**<br>pants: 2011 Maroon Egg Bowl | helmet back **E2**, helmet front **E**, helmet right **E**, jersey back **D**, jersey front **D**, jersey left **all**, pants front **all**, pants left **all** |
| 5 | Mississippi State | helmet: 2025 Black<br>jersey: 2025 Black **0**<br>pants: 2025 Black | helmet back **F**, helmet front **F**, helmet right **F**, jersey back **E**, jersey front **E**, jersey left **all**, pants front **all**, pants left **all** |
| 6 | Mississippi State | helmet: 1949 White<br>jersey: 1949 White **12**<br>pants: 1949 White | helmet back **BCD**, helmet front **B**, helmet right **B**, jersey back **A**, jersey front **A**, pants front **all**, pants left **all** |
| 7 | Mississippi State | helmet: 1958 White<br>jersey: 1958 White **12**<br>pants: 1953 Maroon | helmet back **BCD**, helmet front **C**, helmet right **C**, jersey back **A**, jersey front **A**, pants front **all**, pants left **all** |
| 8 | Raleigh | helmet: 1995 Maroon<br>jersey: 1995 Maroon **4**<br>pants: 1995 Maroon | helmet back **BCD**, helmet front **D**, helmet right **D**, jersey back **B**, jersey front **B**, pants front **all**, pants left **all** |
| 9 | MGCCC | helmet: 2025 White<br>jersey: 2025 White **1**<br>pants: 2025 White | helmet back **F**, helmet front **F**, helmet right **F**, jersey back **N2**, jersey front **N2**, jersey left **all**, pants front **all**, pants left **all** |
| 10 | Northwest | helmet: 2015 Navy<br>jersey: 2015 Gray **1**<br>pants: 2016 Gray | helmet back **E**, helmet front **E**, helmet right **E**, jersey back **N3**, jersey front **N3**, jersey left **all**, pants front **all**, pants left **all** |
| 11 | Jones | helmet: 2017 Cardinal<br>jersey: 2017 Cardinal **1**<br>pants: 2017 Gold | helmet back **E**, helmet front **E**, helmet right **E**, jersey back **UA1**, jersey front **UA1**, jersey left **all**, pants front **all**, pants left **all** |
| 12 | MGCCC | helmet: 2015 White<br>jersey: 2015 White **1**<br>pants: 2015 White | helmet back **E**, helmet front **E**, helmet right **E**, jersey back **D**, jersey front **N1**, jersey left **all**, pants front **all**, pants left **all** |
| 13 | Mississippi State | helmet: 1939 Maroon<br>jersey: 1939 Maroon **4**<br>pants: 1939 Maroon | _explicit: helmet/left_ |

### `condensed` — 11 examples + 1 explicit
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | helmet: 1939 Maroon<br>jersey: 1939 Maroon **4**<br>pants: 1939 Maroon | helmet right **A**, jersey front **A**, pants left **all** |
| 2 | Mississippi State | helmet: 1949 White<br>jersey: 1949 White **12**<br>pants: 1949 White | helmet right **B**, jersey front **A**, pants left **all** |
| 3 | Mississippi State | helmet: 1958 White<br>jersey: 1958 White **12**<br>pants: 1953 Maroon | helmet right **C**, jersey front **A**, pants left **all** |
| 4 | Mississippi State | helmet: 2004 White<br>jersey: 2004 White **12**<br>pants: 2004 White | helmet right **D**, jersey front **C**, pants left **all** |
| 5 | Mississippi State | helmet: 2012 Maroon<br>jersey: 2012 Maroon **15**<br>pants: 2012 Maroon | helmet right **E**, jersey front **D**, pants left **all** |
| 6 | Mississippi State | helmet: 2025 Black<br>jersey: 2025 Black **0**<br>pants: 2025 Black | helmet right **F**, jersey front **E**, pants left **all** |
| 7 | Raleigh | helmet: 1995 Maroon<br>jersey: 1995 Maroon **4**<br>pants: 1995 Maroon | helmet right **D**, jersey front **B**, pants left **all** |
| 8 | MGCCC | helmet: 2015 White<br>jersey: 2015 White **1**<br>pants: 2015 White | helmet right **E**, jersey front **N1**, pants left **all** |
| 9 | MGCCC | helmet: 2025 White<br>jersey: 2025 White **1**<br>pants: 2025 White | helmet right **F**, jersey front **N2**, pants left **all** |
| 10 | Northwest | helmet: 2015 Navy<br>jersey: 2015 Gray **1**<br>pants: 2016 Gray | helmet right **E**, jersey front **N3**, pants left **all** |
| 11 | Jones | helmet: 2017 Cardinal<br>jersey: 2017 Cardinal **1**<br>pants: 2017 Gold | helmet right **E**, jersey front **UA1**, pants left **all** |
| 12 | Mississippi State | helmet: 1939 Maroon<br>jersey: 1939 Maroon **4**<br>pants: 1939 Maroon | _explicit: helmet/left_ |

### `helmets-3` — 7 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | helmet: 1939 Maroon | helmet back **A**, helmet front **A**, helmet right **A** |
| 2 | Mississippi State | helmet: 2008 White BCA | helmet back **BCD**, helmet front **D**, helmet right **D** |
| 3 | Mississippi State | helmet: 2014 Maroon DWS100 | helmet back **E**, helmet front **E**, helmet right **E** |
| 4 | Mississippi State | helmet: 2011 Maroon | helmet back **E2**, helmet front **E**, helmet right **E** |
| 5 | Mississippi State | helmet: 2025 Black | helmet back **F**, helmet front **F**, helmet right **F** |
| 6 | Mississippi State | helmet: 1949 White | helmet back **BCD**, helmet front **B**, helmet right **B** |
| 7 | Mississippi State | helmet: 1972 White | helmet back **BCD**, helmet front **C**, helmet right **C** |

### `helmets-4` — 7 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | helmet: 1939 Maroon | helmet back **A**, helmet front **A**, helmet left **A**, helmet right **A** |
| 2 | Mississippi State | helmet: 2008 White BCA | helmet back **BCD**, helmet front **D**, helmet left **D**, helmet right **D** |
| 3 | Mississippi State | helmet: 2014 Maroon DWS100 | helmet back **E**, helmet front **E**, helmet left **E**, helmet right **E** |
| 4 | Mississippi State | helmet: 2011 Maroon | helmet back **E2**, helmet front **E**, helmet left **E**, helmet right **E** |
| 5 | Mississippi State | helmet: 2025 Black | helmet back **F**, helmet front **F**, helmet left **F**, helmet right **F** |
| 6 | Mississippi State | helmet: 1949 White | helmet back **BCD**, helmet front **B**, helmet left **B**, helmet right **B** |
| 7 | Mississippi State | helmet: 1972 White | helmet back **BCD**, helmet front **C**, helmet left **C**, helmet right **C** |

### `jersey-full` — 9 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 1958 Maroon **12** | jersey back **A**, jersey front **A** |
| 2 | Mississippi State | jersey: 1986 Maroon **15** | jersey back **B**, jersey front **B** |
| 3 | Mississippi State | jersey: 2009 Black **14** | jersey back **C**, jersey front **C**, jersey left **all** |
| 4 | Mississippi State | jersey: 2023 Maroon **1** | jersey back **D**, jersey front **D**, jersey left **all** |
| 5 | Mississippi State | jersey: 2025 Black **0** | jersey back **E**, jersey front **E**, jersey left **all** |
| 6 | MGCCC | jersey: 2025 Navy **1** | jersey back **N2**, jersey front **N2**, jersey left **all** |
| 7 | MGCCC | jersey: 2018 Navy **1** | jersey back **N3**, jersey front **N3**, jersey left **all** |
| 8 | Jones | jersey: 2017 Cardinal **1** | jersey back **UA1**, jersey front **UA1**, jersey left **all** |
| 9 | Jones | jersey: 2015 Gray **1** | jersey back **D**, jersey front **N1**, jersey left **all** |

### `pants-full` — 1 example
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | pants: 2025 Black | pants front **all**, pants left **all** |

### `icons-horizontal` — 1 example
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | helmet: 2025 Black<br>jersey: 2025 Black **0**<br>pants: 2025 Black | helmet icon **all**, jersey icon **all**, pants icon **all** |

### `icons-vertical` — 1 example
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | helmet: 2025 Black<br>jersey: 2025 Black **0**<br>pants: 2025 Black | helmet icon **all**, jersey icon **all**, pants icon **all** |


## Mens Basketball

### `mbk-jersey` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 1971 Maroon **45** | jersey back **a**, jersey front **a** |
| 2 | Mississippi State | jersey: 1985 Maroon **5** | jersey back **b**, jersey front **b** |
| 3 | Mississippi State | jersey: 2027 Maroon **1** | jersey back **c**, jersey front **c** |

### `mbk-shorts` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | shorts: 1990 White | shorts left **a**, shorts right **a** |
| 2 | Mississippi State | shorts: 1991 Maroon | shorts left **b**, shorts right **b** |
| 3 | Mississippi State | shorts: 2027 Maroon | shorts left **c**, shorts right **c** |

### `mbk-full` — 4 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 1971 Maroon **45**<br>shorts: 1971 Maroon | jersey back **a**, jersey front **a**, shorts left **a**, shorts right **a** |
| 2 | Mississippi State | jersey: 1985 Maroon **5**<br>shorts: 1985 Maroon | jersey back **b**, jersey front **b**, shorts left **a**, shorts right **a** |
| 3 | Mississippi State | jersey: 2027 Maroon **1**<br>shorts: 2027 Maroon | jersey back **c**, jersey front **c**, shorts left **c**, shorts right **c** |
| 4 | Mississippi State | jersey: 1991 Maroon **21**<br>shorts: 1991 Maroon | jersey back **c**, jersey front **c**, shorts left **b**, shorts right **b** |

### `mbk-condensed` — 4 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 1971 Maroon **45**<br>shorts: 1971 Maroon | jersey front **a**, shorts left **a** |
| 2 | Mississippi State | jersey: 1985 Maroon **5**<br>shorts: 1985 Maroon | jersey front **b**, shorts left **a** |
| 3 | Mississippi State | jersey: 2027 Maroon **1**<br>shorts: 2027 Maroon | jersey front **c**, shorts left **c** |
| 4 | Mississippi State | jersey: 1991 Maroon **21**<br>shorts: 1991 Maroon | jersey front **c**, shorts left **b** |

### `mbk-tall` — 4 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 1971 Maroon **45**<br>shorts: 1971 Maroon | jersey back **a**, jersey front **a**, shorts left **a**, shorts right **a** |
| 2 | Mississippi State | jersey: 1985 Maroon **5**<br>shorts: 1985 Maroon | jersey back **b**, jersey front **b**, shorts left **a**, shorts right **a** |
| 3 | Mississippi State | jersey: 2027 Maroon **1**<br>shorts: 2027 Maroon | jersey back **c**, jersey front **c**, shorts left **c**, shorts right **c** |
| 4 | Mississippi State | jersey: 1991 Maroon **21**<br>shorts: 1991 Maroon | jersey back **c**, jersey front **c**, shorts left **b**, shorts right **b** |

### `mbk-tall-condensed` — 4 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 1971 Maroon **45**<br>shorts: 1971 Maroon | jersey front **a**, shorts right **a** |
| 2 | Mississippi State | jersey: 1985 Maroon **5**<br>shorts: 1985 Maroon | jersey front **b**, shorts right **a** |
| 3 | Mississippi State | jersey: 2027 Maroon **1**<br>shorts: 2027 Maroon | jersey front **c**, shorts right **c** |
| 4 | Mississippi State | jersey: 1991 Maroon **21**<br>shorts: 1991 Maroon | jersey front **c**, shorts right **b** |


## Soccer

### `soccer-jersey` — 1 example
_Constraint: uniform 1: no ls jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 Blue Keeper **0** | jersey back **ss**, jersey front **ss** |

### `soccer-jersey-ls` — 1 example
_Constraint: uniform 1: jersey ls only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2022 Green Keeper **1** | jersey back **ls**, jersey front **ls** |

### `soccer-shorts` — 1 example
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | shorts: 2026 Blue | shorts back **all**, shorts front **all** |

### `soccer-full` — 1 example
_Constraint: uniform 1: no ls jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 White **4**<br>shorts: 2026 White | jersey back **ss**, jersey front **ss**, shorts back **all**, shorts front **all** |

### `soccer-full-ls` — 1 example
_Constraint: uniform 1: jersey ls only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2018 Green Long Sleeve Keeper **0**<br>shorts: 2018 Green | jersey back **ls**, jersey front **ls**, shorts back **all**, shorts front **all** |

### `soccer-condensed` — 1 example
_Constraint: uniform 1: no ls jerseys_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 White **4**<br>shorts: 2026 White | jersey front **ss**, shorts front **all** |

### `soccer-condensed-ls` — 1 example
_Constraint: uniform 1: jersey ls only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2018 Green Long Sleeve Keeper **0**<br>shorts: 2018 Green | jersey front **ls**, shorts front **all** |

### `soccer-combo` — 1 example
_Constraint: uniform 1: jersey ss only, field jersey; uniform 2: jersey ss only, keeper jersey_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 White **4**<br>shorts: 2026 White<br>#2 jersey: 2026 Blue Keeper **0**<br>#2 shorts: 2026 Blue | jersey back **ss**, jersey front **ss**, shorts back **all**, shorts front **all**, #2 jersey back **ss**, #2 jersey front **ss**, #2 shorts back **all**, #2 shorts front **all** |

### `soccer-condensed-combo` — 2 examples
_Constraint: uniform 1: jersey ss only, field jersey; uniform 2: keeper jersey_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 White **4**<br>shorts: 2026 White<br>#2 jersey: 2026 Blue Keeper **0**<br>#2 shorts: 2026 Blue | jersey front **ss**, shorts front **all**, #2 jersey front **ss**, #2 shorts front **all** |
| 2 | Mississippi State | jersey: 2018 Maroon **20**<br>shorts: 2018 Maroon<br>#2 jersey: 2018 Green Long Sleeve Keeper **0**<br>#2 shorts: 2018 Green | jersey front **ss**, shorts front **all**, #2 jersey front **ls**, #2 shorts front **all** |

### `soccer-combo-ls` — 1 example
_Constraint: uniform 1: jersey ss only, field jersey; uniform 2: jersey ls only, keeper jersey_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2018 Maroon **20**<br>shorts: 2018 Maroon<br>#2 jersey: 2018 Green Long Sleeve Keeper **0**<br>#2 shorts: 2018 Green | jersey back **ss**, jersey front **ss**, shorts back **all**, shorts front **all**, #2 jersey back **ls**, #2 jersey front **ls**, #2 shorts back **all**, #2 shorts front **all** |


## Softball

### `diamond-pants` — 2 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | pants: 2023 Black | pants left **blt**, pants right **blt** |
| 2 | Mississippi State | pants: 2026 Black | pants left **std**, pants right **std** |

### `softball-full` — 2 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 Gray **4**<br>pants: 2026 Gray | jersey back **std**, jersey front **std**, pants left **std**, pants right **std** |
| 2 | Mississippi State | jersey: 2023 White Teal Trim **7**<br>pants: 2023 White | jersey back **std**, jersey front **std**, pants left **blt**, pants right **blt** |

### `softball-condensed` — 2 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 Gray **4**<br>pants: 2026 Gray | jersey front **std**, pants left **std** |
| 2 | Mississippi State | jersey: 2023 White Teal Trim **7**<br>pants: 2023 White | jersey front **std**, pants left **blt** |

### `softball-tall` — 2 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 Gray **4**<br>pants: 2026 Gray | jersey back **std**, jersey front **std**, pants left **std**, pants right **std** |
| 2 | Mississippi State | jersey: 2023 White Teal Trim **7**<br>pants: 2023 White | jersey back **std**, jersey front **std**, pants left **blt**, pants right **blt** |


## Volleyball

### `volleyball-jersey` — 2 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2024 Pink **3** | jersey back **ls**, jersey front **ls** |
| 2 | Mississippi State | jersey: 2026 Maroon **1** | jersey back **ss**, jersey front **ss** |

### `volleyball-combo` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2023 Black **3**<br>#2 jersey: 2023 Gray **2** | jersey back **ls**, jersey front **ls**, #2 jersey back **ls**, #2 jersey front **ls** |
| 2 | Mississippi State | jersey: 2023 Maroon **1**<br>#2 jersey: 2023 Black **3** | jersey back **ss**, jersey front **ss**, #2 jersey back **ls**, #2 jersey front **ls** |
| 3 | Mississippi State | jersey: 2026 Maroon **1**<br>#2 jersey: 2026 Maroon **1** | jersey back **ss**, jersey front **ss**, #2 jersey back **ss**, #2 jersey front **ss** |

### `volleyball-condensed-combo-ss-ss` — 1 example
_Constraint: uniform 1: jersey ss only; uniform 2: jersey ss only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2026 Maroon **1**<br>#2 jersey: 2025 White **4** | jersey front **ss**, #2 jersey front **ss** |

### `volleyball-condensed-combo-ss-ls` — 1 example
_Constraint: uniform 1: jersey ss only; uniform 2: jersey ls only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2023 Maroon **1**<br>#2 jersey: 2023 Black **3** | jersey front **ss**, #2 jersey front **ls** |

### `volleyball-condensed-combo-ls-ss` — 1 example
_Constraint: uniform 1: jersey ls only; uniform 2: jersey ss only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2023 Black **3**<br>#2 jersey: 2023 Maroon **1** | jersey front **ls**, #2 jersey front **ss** |

### `volleyball-condensed-combo-ls-ls` — 1 example
_Constraint: uniform 1: jersey ls only; uniform 2: jersey ls only_

| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2023 Black **3**<br>#2 jersey: 2023 Gray **2** | jersey front **ls**, #2 jersey front **ls** |


## Womens Basketball

### `wbk-jersey` — 1 example
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2025 Black **15** | jersey back **all**, jersey front **all** |

### `wbk-shorts` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | shorts: 2025 Maroon | shorts back **a**, shorts front **a** |
| 2 | Mississippi State | shorts: 2025 White Pink | shorts back **b**, shorts front **b** |
| 3 | Mississippi State | shorts: 2025 Black | shorts back **c**, shorts front **c** |

### `wbk-full` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2025 Black **15**<br>shorts: 2025 Black | jersey back **all**, jersey front **all**, shorts back **c**, shorts front **c** |
| 2 | Mississippi State | jersey: 2025 Maroon **2**<br>shorts: 2025 Maroon | jersey back **all**, jersey front **all**, shorts back **a**, shorts front **a** |
| 3 | Mississippi State | jersey: 2025 White Pink **21**<br>shorts: 2025 White Pink | jersey back **all**, jersey front **all**, shorts back **b**, shorts front **b** |

### `wbk-condensed` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2025 Black **15**<br>shorts: 2025 Black | jersey front **all**, shorts front **c** |
| 2 | Mississippi State | jersey: 2025 Maroon **2**<br>shorts: 2025 Maroon | jersey front **all**, shorts front **a** |
| 3 | Mississippi State | jersey: 2025 White Pink **21**<br>shorts: 2025 White Pink | jersey front **all**, shorts front **b** |

### `wbk-tall` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2025 Black **15**<br>shorts: 2025 Black | jersey back **all**, jersey front **all**, shorts back **c**, shorts front **c** |
| 2 | Mississippi State | jersey: 2025 Maroon **2**<br>shorts: 2025 Maroon | jersey back **all**, jersey front **all**, shorts back **a**, shorts front **a** |
| 3 | Mississippi State | jersey: 2025 White Pink **21**<br>shorts: 2025 White Pink | jersey back **all**, jersey front **all**, shorts back **b**, shorts front **b** |

### `wbk-tall-condensed` — 3 examples
| # | team | elements | eras covered |
|---|---|---|---|
| 1 | Mississippi State | jersey: 2025 Black **15**<br>shorts: 2025 Black | jersey front **all**, shorts front **c** |
| 2 | Mississippi State | jersey: 2025 Maroon **2**<br>shorts: 2025 Maroon | jersey front **all**, shorts front **a** |
| 3 | Mississippi State | jersey: 2025 White Pink **21**<br>shorts: 2025 White Pink | jersey front **all**, shorts front **b** |