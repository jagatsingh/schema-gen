/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 * Generated from: CanonicalOrder
 * Generator: schema-gen Jackson generator
 *
 * To regenerate this file, run:
 *     schema-gen generate --target jackson
 *
 * Changes to this file will be overwritten.
 */

package com.example.models;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;
import java.util.List;
import java.util.Map;
import javax.validation.constraints.NotNull;

/**
 * Order placed against the matching engine.
 *
 * Carries the instrument identifier, the side (BUY/SELL), and an optional
 * client-supplied tag. Used as a fixture for cross-generator output
 * stability tests.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonPropertyOrder({"instrument", "quantity", "price", "side", "tag", "metadata", "fills"})
public class CanonicalOrder {

    /**
     * Exchange-prefixed symbol
     */
    @JsonProperty("instrument")
    @NotNull
    private String instrument;

    /**
     * Number of contracts
     */
    @JsonProperty("quantity")
    @NotNull
    private int quantity;

    /**
     * Limit price
     */
    @JsonProperty("price")
    @NotNull
    private double price;

    /**
     * Buy or sell
     */
    @JsonProperty("side")
    @NotNull
    private String side;

    /**
     * Optional client tag
     */
    @JsonProperty("tag")
    private String tag;

    /**
     * Free-form metadata
     */
    @JsonProperty("metadata")
    @NotNull
    private Map<String, Object> metadata;

    /**
     * Per-fill prices (FIFO)
     */
    @JsonProperty("fills")
    @NotNull
    private List<Double> fills;

    // Constructors
    public CanonicalOrder() {}

    public CanonicalOrder(String instrument, int quantity, double price, String side, String tag, Map<String, Object> metadata, List<Double> fills) {
        this.instrument = instrument;
        this.quantity = quantity;
        this.price = price;
        this.side = side;
        this.tag = tag;
        this.metadata = metadata;
        this.fills = fills;
    }

    // Getters and Setters

    public String getInstrument() {
        return instrument;
    }

    public void setInstrument(String instrument) {
        this.instrument = instrument;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public double getPrice() {
        return price;
    }

    public void setPrice(double price) {
        this.price = price;
    }

    public String getSide() {
        return side;
    }

    public void setSide(String side) {
        this.side = side;
    }

    public String getTag() {
        return tag;
    }

    public void setTag(String tag) {
        this.tag = tag;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }

    public List<Double> getFills() {
        return fills;
    }

    public void setFills(List<Double> fills) {
        this.fills = fills;
    }
}
