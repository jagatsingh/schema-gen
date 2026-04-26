/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 * Generated from: CanonicalOrder
 * Generator: schema-gen Kotlin generator
 *
 * To regenerate this file, run:
 *     schema-gen generate --target kotlin
 *
 * Changes to this file will be overwritten.
 */

package com.example.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Order placed against the matching engine.

Carries the instrument identifier, the side (BUY/SELL), and an optional
client-supplied tag. Used as a fixture for cross-generator output
stability tests.
 */
@Serializable
data class CanonicalOrder(
    val instrument: String,  // Exchange-prefixed symbol
    val quantity: Long,  // Number of contracts
    val price: Double,  // Limit price
    val side: String,  // Buy or sell
    val tag: String? = null,  // Optional client tag
    val metadata: Map<String, Any>,  // Free-form metadata
    val fills: List<Double> = emptyList()  // Per-fill prices (FIFO)
)
