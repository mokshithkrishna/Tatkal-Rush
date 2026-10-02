package mypackage;

public class BankAccount {

    // Public data members
    public String accHolder;
    public String accNumber;

    // Private data members
    private double bal;
    private String pin;
    private String accType;

    // Protected data members
    protected String bankName;
    protected String branchName;

    // Constructor
    public BankAccount() {
        bankName = "State Bank";
        branchName = "Rajapalayam";
        accType = "Savings";
        pin = "4747";
        bal = 0.0;
    }

    // Deposit method
    public void deposit(double amount) {
        if (amount > 0) {
            bal += amount;
            System.out.println("Deposit Successful!");
        } else {
            System.out.println("Invalid Deposit Amount.");
        }
    }

    // Display method
    public void displayBalance() {
        System.out.println("Bank Name      : " + bankName);
        System.out.println("Branch Name    : " + branchName);
        System.out.println("Account Holder : " + accHolder);
        System.out.println("Account Number : " + accNumber);
        System.out.println("Account Type   : " + accType);
        System.out.println("Current Balance: Rs. " + bal);
    }
}