"use strict";

const form = document.getElementById("listingForm");
const descriptionInput = document.getElementById("description");
const termsCheckbox = document.getElementById("termsAccepted");
const submissionStatus = document.getElementById("submissionStatus");

const validateForm = () => {
    const description = descriptionInput.value.trim();

    if (description.length <= 25) {
        alert("The listing description must contain more than 25 characters.");
        return false;
    }

    if (!termsCheckbox.checked) {
        alert("You must agree to the terms and conditions.");
        return false;
    }

    return true;
};

const createSubmissionCounter = () => {
    let count = 0;

    return () => {
        count += 1;
        return count;
    };
};

const trackSuccessfulSubmission = createSubmissionCounter();

form.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!validateForm()) {
        return;
    }

    const formData = Object.fromEntries(new FormData(form));
    formData.termsAccepted = termsCheckbox.checked;

    const jsonString = JSON.stringify(formData);
    console.log("JSON string:", jsonString);

    const parsedObject = JSON.parse(jsonString);

    const { title, email } = parsedObject;
    console.log("Primary field - Listing title:", title);
    console.log("Submitter email:", email);

    const updatedObject = {
        ...parsedObject,
        submissionDate: new Date().toISOString()
    };

    console.log("Updated parsed object:", updatedObject);

    const submissionCount = trackSuccessfulSubmission();
    console.log("Successful submission count:", submissionCount);

    submissionStatus.textContent =
        `Listing submitted successfully. Submission count: ${submissionCount}`;

    form.reset();
    document.getElementById("title").focus();
});