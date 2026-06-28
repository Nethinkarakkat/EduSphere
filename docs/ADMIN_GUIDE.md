# Admin Guide

This guide provides comprehensive instructions for administrators using EduSphere to manage the examination system.

## Table of Contents

- [Getting Started](#getting-started)
- [Dashboard Overview](#dashboard-overview)
- [User Management](#user-management)
- [Faculty Approval](#faculty-approval)
- [Classroom Management](#classroom-management)
- [Exam Oversight](#exam-oversight)
- [Reports and Analytics](#reports-and-analytics)
- [Activity Monitoring](#activity-monitoring)
- [Profile Management](#profile-management)
- [Best Practices](#best-practices)

## Getting Started

### Default Admin Login

- **Email:** `admin@mail.com`
- **Password:** `admin`

⚠️ **Important:** Change your password immediately after first login!

### First-Time Setup

1. Log in with default credentials
2. Navigate to **Profile** → **Change Password**
3. Set a strong password (minimum 6 characters)
4. Review system settings
5. Add faculty accounts
6. Approve pending faculty registrations

## Dashboard Overview

The admin dashboard provides a comprehensive overview of the entire system:

### Key Metrics

- **Total Students:** Number of registered student accounts
- **Total Faculty:** Number of faculty accounts (including pending)
- **Active Faculty:** Number of approved faculty members
- **Pending Faculty:** Faculty awaiting approval
- **Total Exams:** Number of exams created in the system
- **Active Classrooms:** Number of active classrooms
- **Active Exams:** Currently running exams
- **Total Submissions:** Total exam submissions across all exams
- **Pending Results:** Exams with unpublished results

### Recent Activity

View the latest 8 system activities including:
- User registrations
- Exam creation
- Result publications
- Profile updates

### Quick Actions

Access frequently used features:
- Add new users
- View all users
- View activity logs
- Generate reports

## User Management

### Adding Users

1. Navigate to **Users** from the dashboard
2. Click **"Add User"**
3. Fill in the required information:
   - **Name:** Full name of the user
   - **Email:** Unique email address
   - **Password:** Initial password (user can change later)
   - **Role:** Select from Admin, Faculty, or Student
4. Click **"Add User"**

**Note:** Admin accounts cannot be created through the signup page. Only admins can create admin accounts.

### Viewing Users

1. Navigate to **Users**
2. Use filters to find specific users:
   - **Search:** Search by name or email
   - **Role:** Filter by user role
   - **Status:** Filter by approval status
   - **Sort:** Sort by name, email, or creation date
3. Click on any user to view detailed information

### Editing Users

1. Navigate to **Users**
2. Click on the user you want to edit
3. Click **"Edit User"**
4. Update the required fields
5. Click **"Update User"**

### Deleting Users

1. Navigate to **Users**
2. Click on the user you want to delete
3. Click **"Delete User"**
4. Confirm the deletion

⚠️ **Warning:** Deleting a user will:
- Remove all their data
- Remove them from all classrooms
- Delete their exam submissions
- This action cannot be undone

### Viewing User Details

Click on any user to view:
- **Personal Information:** Name, email, phone, date of birth
- **Account Details:** Role, approval status, creation date
- **Classrooms:** Classrooms they're enrolled in (students) or manage (faculty)
- **Exam History:** Exams attempted (students) or created (faculty)
- **Activity Log:** Recent actions performed by the user

## Faculty Approval

### Approving Faculty

Faculty accounts require admin approval before they can access the system:

1. Navigate to **Users**
2. Filter by **Role: Faculty** and **Status: Pending**
3. Click on the pending faculty account
4. Review their information
5. Click **"Approve User"**
6. The faculty will receive access to their dashboard

### Rejecting Faculty

If a faculty registration is not appropriate:

1. Navigate to **Users**
2. Click on the pending faculty account
3. Click **"Delete User"**
4. Confirm the deletion

## Classroom Management

### Viewing All Classrooms

1. Navigate to **Classrooms** from the dashboard
2. View all classrooms in the system including:
   - Classroom name and subject
   - Faculty name
   - Number of enrolled students
   - Creation date

### Viewing Classroom Details

1. Click on any classroom to view details
2. See:
   - Classroom information
   - Enrolled students
   - Associated exams
   - Student submissions

⚠️ **Note:** Admins cannot create, edit, or delete classrooms. These actions are reserved for faculty members.

## Exam Oversight

### Viewing All Exams

1. Navigate to **Exams** from the dashboard
2. View all exams in the system including:
   - Exam title and subject
   - Faculty name
   - Exam date
   - Status (Draft, Launched, Published)
   - Number of questions

### Filtering Exams

Use filters to find specific exams:
- **Status:** Filter by exam status
- **Faculty:** Filter by faculty member

### Exam Status

- **Draft:** Exam created but not yet launched
- **Launched:** Exam is live and students can attempt it
- **Published:** Results have been published

## Reports and Analytics

### Generating Reports

1. Navigate to **Reports** from the dashboard
2. Use filters to customize the report:
   - **Student:** Filter by specific student
   - **Exam:** Filter by specific exam
   - **Faculty:** Filter by specific faculty
3. Click **"Generate Report"**

### Report Data

Reports include:
- **Performance Statistics:** Average scores, pass rates
- **Top Performers:** Students with highest scores
- **Low Performers:** Students needing improvement
- **Faculty Statistics:** Performance by faculty member
- **Classroom Statistics:** Performance by classroom

### Exporting Reports

#### CSV Export

1. Generate the desired report
2. Click **"Export to CSV"**
3. The file will download automatically

#### PDF Export

1. Generate the desired report
2. Click **"Export to PDF"**
3. The file will download automatically

### Report Filters

- **Student:** Analyze individual student performance
- **Exam:** Analyze performance on specific exams
- **Faculty:** Compare performance across faculty members

## Activity Monitoring

### Viewing Activity Logs

1. Navigate to **Activity** from the dashboard
2. View all system activities including:
   - User actions (login, logout, profile updates)
   - Exam creation and modifications
   - Result publications
   - Classroom management

### Filtering Activity Logs

Use filters to find specific activities:
- **Search:** Search by action description
- **Role:** Filter by user role
- **Date Range:** Filter by date range

### Activity Types

- **User Registration:** New account creation
- **Profile Updates:** Changes to user profiles
- **Exam Creation:** New exams created
- **Exam Launch:** Exams made live
- **Result Publication:** Results published
- **Classroom Creation:** New classrooms created
- **Login/Logout:** User authentication events

## Profile Management

### Viewing Profile

1. Navigate to **Profile** from the top menu
2. View your account information:
   - Name and email
   - Role
   - Profile picture
   - Account creation date

### Changing Password

1. Navigate to **Profile** → **Change Password**
2. Enter your current password
3. Enter your new password (minimum 6 characters)
4. Confirm your new password
5. Click **"Change Password"**

### Updating Profile Picture

1. Navigate to **Profile**
2. Click **"Upload Picture"**
3. Select an image file (JPG, JPEG, PNG)
4. Crop the image as desired
5. Click **"Save"**

**File Requirements:**
- Maximum size: 2MB
- Accepted formats: JPG, JPEG, PNG

### Removing Profile Picture

1. Navigate to **Profile**
2. Click **"Remove Picture"**
3. Confirm the removal

## Best Practices

### Security

1. **Strong Passwords:** Use strong, unique passwords for all accounts
2. **Regular Updates:** Change passwords periodically
3. **Access Control:** Only approve verified faculty members
4. **Monitor Activity:** Regularly review activity logs for suspicious behavior

### User Management

1. **Verify Information:** Verify faculty credentials before approval
2. **Regular Cleanup:** Remove inactive accounts periodically
3. **Role Assignment:** Assign appropriate roles based on responsibilities
4. **Documentation:** Keep records of user approvals and deletions

### System Maintenance

1. **Regular Backups:** Ensure regular database backups
2. **Monitor Performance:** Watch for system performance issues
3. **Update Dependencies:** Keep Python packages updated
4. **Review Logs:** Regularly review system logs

### Communication

1. **Notify Users:** Inform users of system changes
2. **Provide Training:** Train faculty on system usage
3. **Support Channel:** Establish a support channel for users
4. **Documentation:** Keep user guides updated

## Troubleshooting

### Common Issues

#### User Cannot Login

- Verify email and password are correct
- Check if account is approved (faculty)
- Ensure account is not deleted
- Reset password if necessary

#### Faculty Not Receiving Approval Email

- Check email configuration
- Verify email address is correct
- Manually approve through admin panel

#### Reports Not Generating

- Verify database connection
- Check for sufficient data
- Ensure filters are correctly applied

#### Activity Logs Not Updating

- Check database connection
- Verify logging configuration
- Restart the application if necessary

## Tips and Tricks

### Efficient User Management

- Use bulk operations when possible
- Create user templates for common roles
- Regularly review pending approvals

### Effective Monitoring

- Set up regular activity log reviews
- Create custom report templates
- Use filters to focus on specific metrics

### System Optimization

- Archive old data regularly
- Clean up unused accounts
- Optimize database queries

## Support

For additional support:

1. Check the [Installation Guide](INSTALLATION.md)
2. Review the [Deployment Guide](DEPLOYMENT.md)
3. Consult the [API Documentation](API_DOCUMENTATION.md)
4. Open an issue on GitHub

## Summary

As an admin, you have complete control over the EduSphere system. Your responsibilities include:

- Managing user accounts
- Approving faculty registrations
- Monitoring system activity
- Generating reports
- Ensuring system security
- Providing support to users

Regular monitoring and maintenance will ensure the system runs smoothly and securely.
