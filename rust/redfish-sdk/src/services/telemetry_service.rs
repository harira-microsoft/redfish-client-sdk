// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use crate::context::ClientContext;
use crate::errors::RedfishError;
use crate::protocol::response::RedfishResponse;

pub struct TelemetryServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> TelemetryServiceHandle<'ctx> {
    pub(crate) fn new(ctx: &'ctx ClientContext) -> Self { Self { ctx } }

    fn service_uri(&self) -> String {
        self.ctx.resolve_service_uri("TelemetryService", "/TelemetryService")
    }

    // ── Async ────────────────────────────────────────────────────────────────

    pub async fn get_service_info(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(&self.service_uri()).await
    }

    pub async fn list_metric_report_definitions(&self) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/MetricReportDefinitions", self.service_uri());
        self.ctx.get(&uri).await
    }

    pub async fn get_metric_report_definition(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(uri).await
    }

    pub async fn list_metric_reports(&self) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/MetricReports", self.service_uri());
        self.ctx.get(&uri).await
    }

    pub async fn get_metric_report(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(uri).await
    }

    // ── Blocking wrappers ────────────────────────────────────────────────────

    pub fn get_service_info_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_service_info())
    }
    pub fn list_metric_report_definitions_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_metric_report_definitions())
    }
    pub fn get_metric_report_definition_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_metric_report_definition(uri))
    }
    pub fn list_metric_reports_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_metric_reports())
    }
    pub fn get_metric_report_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_metric_report(uri))
    }
}
