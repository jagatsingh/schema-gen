// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
// Generated from: CanonicalOrder
// Generator: schema-gen Rust Serde generator
//
// To regenerate: schema-gen generate --target rust

use serde::{Deserialize, Serialize};
use schemars::JsonSchema;

/// Two-sided trade direction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, JsonSchema)]
pub enum CanonicalSide {
    #[serde(rename = "buy")]
    Buy,
    #[serde(rename = "sell")]
    Sell,
}

/// Order placed against the matching engine.
/// 
/// Carries the instrument identifier, the side (BUY/SELL), and an optional
/// client-supplied tag. Used as a fixture for cross-generator output
/// stability tests.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CanonicalOrder {
    /// Exchange-prefixed symbol
    pub instrument: String,

    /// Number of contracts
    pub quantity: i64,

    /// Limit price
    pub price: f64,

    /// Buy or sell
    pub side: CanonicalSide,

    /// Optional client tag
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tag: Option<String>,

    /// Free-form metadata
    pub metadata: serde_json::Value,

    /// Per-fill prices (FIFO)
    pub fills: Vec<f64>,
}
