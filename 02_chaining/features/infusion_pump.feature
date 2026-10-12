Feature: REQ-101 Air Bubble Detection and Infusion Pump Safety

  Scenario: Infusion pump stops and raises alarm when air bubble is detected
    Given the pump is infusing
    When an air bubble is detected
    Then the infusion should stop
    Then a high-priority alarm should sound

  Scenario: User can silence the alarm for 2 minutes
    Given the pump is infusing
    When an air bubble is detected
    Then a high-priority alarm should sound
    When the user silences the alarm
    Then the alarm should be silenced for 2 minutes

  Scenario: Infusion does not resume after alarm silence timeout
    Given the pump is infusing
    When an air bubble is detected
    Then a high-priority alarm should sound
    When the user silences the alarm
    Then the alarm should be silenced for 2 minutes
    Then the infusion should remain stopped

  Scenario: Infusion resumes only after air bubble is cleared by user
    Given the pump is infusing
    When an air bubble is detected
    Then the infusion should stop
    When the user clears the air bubble
    Then the infusion should remain stopped
    When the user silences the alarm
    Then the alarm should be silenced for 2 minutes
    When the user clears the air bubble
    Then the infusion should remain stopped