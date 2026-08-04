# build_sorted_vars.R
#
# Rebuild the UI-choice caches used by both PharmaTRACE dashboards from the
# refreshed import and export parquet files.
#
# Run from the PharmaTRACE project directory after build_parquet.R:
#   Rscript build_sorted_vars.R

suppressPackageStartupMessages({
  library(DBI)
  library(duckdb)
})

# ---- Configuration ---------------------------------------------------------
datasets <- list(
  Imports = list(
    parquet = file.path(
      "data", "all_CADpharma_imports_1988_2026.parquet"
    ),
    cache = file.path("sortedVars", "sorted_vars.rds"),
    first_year = 1988L,
    last_year = 2026L
  ),
  Exports = list(
    parquet = file.path(
      "data", "all_CADpharma_exports_2000_2026_byMonth.parquet"
    ),
    cache = file.path("sortedVars", "sorted_vars_EXPORTS_2026.rds"),
    first_year = 2000L,
    last_year = 2026L
  )
)

missing_parquets <- vapply(
  datasets,
  function(x) !file.exists(x$parquet),
  logical(1)
)

if (any(missing_parquets)) {
  stop(
    "Could not find the following parquet file(s):\n",
    paste0(
      "  - ",
      vapply(datasets[missing_parquets], `[[`, character(1), "parquet"),
      collapse = "\n"
    ),
    "\nRun this script from the PharmaTRACE project directory after ",
    "build_parquet.R."
  )
}

dir.create("sortedVars", recursive = TRUE, showWarnings = FALSE)

# ---- DuckDB helpers ---------------------------------------------------------
con <- DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:")
on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)

quote_id <- function(x) {
  as.character(DBI::dbQuoteIdentifier(con, x))
}

quote_string <- function(x) {
  as.character(DBI::dbQuoteString(con, x))
}

required_columns <- c(
  "Period", "Province", "Country", "State", "Commodity",
  "unit_of_measure"
)

distinct_values <- function(parquet_source, column) {
  column_sql <- quote_id(column)

  result <- DBI::dbGetQuery(
    con,
    paste0(
      "SELECT DISTINCT TRIM(CAST(", column_sql, " AS VARCHAR)) AS value ",
      "FROM ", parquet_source, " ",
      "WHERE ", column_sql, " IS NOT NULL ",
      "AND TRIM(CAST(", column_sql, " AS VARCHAR)) <> '' ",
      "ORDER BY value"
    )
  )

  result$value
}

build_cache <- function(dataset, trade_flow) {
  parquet_abs <- normalizePath(dataset$parquet, mustWork = TRUE)
  parquet_source <- paste0(
    "parquet_scan(", quote_string(parquet_abs), ")"
  )

  schema <- DBI::dbGetQuery(
    con,
    paste("DESCRIBE SELECT * FROM", parquet_source)
  )
  missing_columns <- setdiff(required_columns, schema$column_name)

  if (length(missing_columns) > 0L) {
    stop(
      trade_flow, " parquet is missing required column(s): ",
      paste(missing_columns, collapse = ", ")
    )
  }

  period_sql <- "TRY_CAST(Period AS DATE)"
  period_audit <- DBI::dbGetQuery(
    con,
    paste0(
      "SELECT ",
      "COUNT(*) AS total_records, ",
      "COUNT(*) - COUNT(", period_sql, ") AS unparsed_periods, ",
      "MIN(YEAR(", period_sql, ")) AS first_year, ",
      "MAX(YEAR(", period_sql, ")) AS last_year ",
      "FROM ", parquet_source
    )
  )

  if (period_audit$total_records[[1L]] == 0) {
    stop(trade_flow, " parquet contains no records.")
  }

  if (period_audit$unparsed_periods[[1L]] > 0) {
    stop(
      trade_flow, " parquet contains ",
      format(period_audit$unparsed_periods[[1L]], big.mark = ","),
      " unparseable Period value(s)."
    )
  }

  observed_first_year <- as.integer(period_audit$first_year[[1L]])
  observed_last_year <- as.integer(period_audit$last_year[[1L]])

  if (
    observed_first_year != dataset$first_year ||
    observed_last_year != dataset$last_year
  ) {
    stop(
      trade_flow, " parquet was expected to span ",
      dataset$first_year, "-", dataset$last_year,
      " but spans ", observed_first_year, "-", observed_last_year, "."
    )
  }

  years <- DBI::dbGetQuery(
    con,
    paste0(
      "SELECT DISTINCT YEAR(", period_sql, ") AS year ",
      "FROM ", parquet_source, " ",
      "WHERE ", period_sql, " IS NOT NULL ",
      "ORDER BY year"
    )
  )$year

  year_months <- DBI::dbGetQuery(
    con,
    paste0(
      "SELECT DISTINCT STRFTIME(", period_sql,
      ", '%Y-%m') AS year_month ",
      "FROM ", parquet_source, " ",
      "WHERE ", period_sql, " IS NOT NULL ",
      "ORDER BY year_month"
    )
  )$year_month

  sorted_vars <- list(
    years = as.integer(years),
    year_months = year_months,
    provinces = distinct_values(parquet_source, "Province"),
    countries = distinct_values(parquet_source, "Country"),
    commodities = distinct_values(parquet_source, "Commodity"),
    states = distinct_values(parquet_source, "State"),
    units = distinct_values(parquet_source, "unit_of_measure")
  )

  saveRDS(sorted_vars, dataset$cache)

  cat("\n", trade_flow, " sorted-variable cache complete.\n", sep = "")
  cat("Parquet:            ", dataset$parquet, "\n", sep = "")
  cat("Cache:              ", dataset$cache, "\n", sep = "")
  cat(
    "Records:            ",
    format(period_audit$total_records[[1L]], big.mark = ",", scientific = FALSE),
    "\n",
    sep = ""
  )
  cat("Year range:         ", min(sorted_vars$years), "-",
      max(sorted_vars$years), "\n", sep = "")
  cat("Provinces:          ", length(sorted_vars$provinces), "\n", sep = "")
  cat("Countries:          ", length(sorted_vars$countries), "\n", sep = "")
  cat("Commodities:        ", length(sorted_vars$commodities), "\n", sep = "")
  cat("States:             ", length(sorted_vars$states), "\n", sep = "")
  cat("Units:              ", length(sorted_vars$units), "\n", sep = "")

  invisible(sorted_vars)
}

# Build both caches in the same run.
invisible(Map(build_cache, datasets, names(datasets)))

cat("\nBoth PharmaTRACE sorted-variable caches were rebuilt successfully.\n")
