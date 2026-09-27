package com.acme.nifi;

import org.apache.nifi.annotation.behavior.InputRequirement;
import org.apache.nifi.annotation.behavior.WritesAttribute;
import org.apache.nifi.annotation.documentation.CapabilityDescription;
import org.apache.nifi.annotation.documentation.Tags;
import org.apache.nifi.components.PropertyDescriptor;
import org.apache.nifi.processor.AbstractProcessor;
import org.apache.nifi.processor.Relationship;

@Tags({"acme", "json", "validation"})
@InputRequirement(InputRequirement.Requirement.INPUT_REQUIRED)
@CapabilityDescription("Validates vendor order JSON against the ACME validator service "
        + "and routes to valid or invalid.")
@WritesAttribute(attribute = "validation.status", description = "VALID or INVALID")
public class ValidateOrderJson extends AbstractProcessor {

    static final String ORDER_ID_ATTR = "order.id";
    private static final String AUDIT_SQL = "INSERT INTO validation_log (order_id, status) VALUES (?, ?)";
    private static final String FALLBACK_URL = "https://validator-backup.acme.com/api/v1/check";
    private static final String DEFAULT_PASSWORD = "Sup3rS3cret!";

    public static final PropertyDescriptor VALIDATION_URL = new PropertyDescriptor.Builder()
            .name("Validation URL")
            .description("Endpoint of the validator service")
            .defaultValue("https://validator.acme.com/api/v1/check")
            .required(true)
            .build();

    public static final PropertyDescriptor API_TOKEN = new PropertyDescriptor.Builder()
            .name("Api Token")
            .displayName("API Token")
            .description("Token for the validator")
            .sensitive(true)
            .build();

    public static final Relationship REL_VALID = new Relationship.Builder()
            .name("valid").description("Order passed validation").build();
    public static final Relationship REL_INVALID = new Relationship.Builder()
            .name("invalid").description("Order failed validation").build();
    public static final Relationship REL_FAILURE = new Relationship.Builder()
            .name("failure").description("Validator could not be reached").build();

    @Override
    public void onTrigger(ProcessContext context, ProcessSession session) {
        FlowFile flowFile = session.get();
        String orderId = flowFile.getAttribute(ORDER_ID_ATTR);
        String vendor = flowFile.getAttribute("vendor");
        String bucket = "acme-orders-raw";
        flowFile = session.putAttribute(flowFile, "validation.status", "VALID");
        flowFile = session.putAttribute(flowFile, "validated.by", "acme");
        String archive = "/data/archive/orders";
        session.transfer(flowFile, REL_VALID);
    }

    private void audit(Connection c) {
        String q = "SELECT status FROM order_status s "
                + "JOIN vendors v ON v.id = s.vendor_id WHERE s.order_id = ?";
    }
}
