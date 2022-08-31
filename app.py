import time
import os
from datetime import datetime

from flask import Flask, request, render_template, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from functools import wraps

import cv2
import numpy as np
import face_recognition
from video_capture import VideoCapture

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db/database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = '8IR4M7-R3c74GjTHhKzWODaYVHuPGqn4w92DHLqeYJA'

db = SQLAlchemy(app)
# Import models here as to avoid circular import issue
from models import *

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login_student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        data = Student.query.filter_by(email=email, password=password).first()

        if data is not None:
            student = Student.query.filter_by(
                email=email, password=password).one()
            session['std_logged_in'] = True
            uname = email.split('@')[0]
            session['uname'] = uname
            session['roll_no'] = student.rollno

            flash('You are now logged in', 'success')
            return redirect(url_for('student'))
        else:
            error = 'Invalid login'
            return render_template('login_student.html', error=error)

    return render_template('login_student.html')


@app.route('/login_faculty', methods=['GET', 'POST'])
def login_faculty():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        data = Faculty.query.filter_by(email=email, password=password).first()
        if data is not None:
            faculty = Faculty.query.filter_by(
                email=email, password=password).one()
            if faculty.is_admin:
                session['is_admin'] = True
            session['fty_logged_in'] = True
            uname = email.split('@')[0]
            session['uname'] = uname
            session['name'] = faculty.name
            session['course'] = faculty.course

            flash('You are now logged in', 'success')
            return redirect(url_for('faculty'))
        else:
            error = 'Invalid login'
            return render_template('login_faculty.html', error=error)

    return render_template('login_faculty.html')


def is_student_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'std_logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login!', 'danger')
            return redirect(url_for('login_student'))
    return wrap


def is_faculty_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'fty_logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login!', 'danger')
            return redirect(url_for('login_faculty'))
    return wrap


@app.route('/student')
@is_student_logged_in
def student():
    courses = Attendance.query.filter_by(rollno=session['roll_no']).with_entities(
        Attendance.course).distinct().order_by(Attendance.course).all()
    lectures_count = []
    for course in courses:
        lec_count = Attendance.query.filter_by(
            rollno=session['roll_no'], course=course[0]).count()
        lectures_count.append(lec_count)
    app.logger.info(lectures_count)
    return render_template('dashboard_student.html', courses=courses, lectures_count=lectures_count)


@app.route('/my_attendance')
@is_student_logged_in
def view_attendance():
    course = request.args.get('course')

    unique_courses = Attendance.query.filter_by(rollno=session['roll_no']).with_entities(
        Attendance.course).distinct().order_by(Attendance.course).all()
    if course is None:
        course = unique_courses[0][0]
    # get unique lecture numbers marked by current faculty
    # get the attendance for the specified lecture
    attendance = Attendance.query.filter_by(
        rollno=session['roll_no'], course=course).all()

    return render_template('view_attendance.html', unique_courses=unique_courses, attendance=attendance)


@app.route('/faculty')
@is_faculty_logged_in
def faculty():
    lectures_count = Attendance.query.filter_by(
        marked_by=session['name']).with_entities(Attendance.lecture_no).distinct().count()
    students_count = Student.query.with_entities(Student.rollno).count()
    faculty_count = Faculty.query.with_entities(Faculty.f_id).count()
    return render_template('dashboard_faculty.html', lectures_count=lectures_count, students_count=students_count, faculty_count=faculty_count)


@app.route('/faculty_registration', methods=['GET', 'POST'])
@is_faculty_logged_in
def register_faculty():
    if request.method == 'POST':
        data = Faculty.query.filter_by(email=request.form['email']).first()
        if 'isAdmin' in request.form:
            is_admin = True
        else:
            is_admin = False
        # if email does not already exist
        if data is None:
            faculty = Faculty(
                name=request.form['name'],
                course=request.form['course'],
                email=request.form['email'],
                password=request.form['password'],
                is_admin=is_admin,
                registered_on=datetime.now()
            )
            db.session.add(faculty)
            db.session.commit()

            flash('Faculty registration successful', 'success')
            return render_template('register_faculty.html')
        else:
            flash('Faculty with this email already exists!', 'danger')
    return render_template('register_faculty.html')


@app.route('/student_registration', methods=['GET', 'POST'])
@is_faculty_logged_in
def register_student():
    if request.method == 'POST':
        data = Student.query.filter_by(email=request.form['email']).first()
        if data is None:
            new_student = Student(
                rollno=request.form['rollno'],
                name=request.form['name'],
                semester=request.form['semester'],
                email=request.form['email'],
                password=request.form['password'],
                pic_path=f'static/images/users/{request.form["rollno"]}-{request.form["name"]}.jpg',
                registered_on=datetime.now()
            )
            db.session.add(new_student)
            db.session.commit()

            if os.path.isfile('static/images/users/temp.jpg'):
                os.rename('static/images/users/temp.jpg',
                          f'static/images/users/{request.form["rollno"]}-{request.form["name"]}.jpg')
            if 'img_captured' in session:
                session.pop('img_captured')
            flash('Student registration successful', 'success')
            return render_template('register_student.html')
        else:
            flash('Student with this email already exists!', 'danger')

    if os.path.isfile('static/images/users/temp.jpg'):
        temp_pic = True
    else:
        temp_pic = False

    return render_template('register_student.html', temp_pic=temp_pic)


@app.route("/capture_image")
@is_faculty_logged_in
def capture_image():
    session['dt'] = datetime.now()
    path = 'static/images/users'
    cap = cv2.VideoCapture(0)

    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()

        # Display the resulting frame
        cv2.imshow('Press c to capture image', frame)
        if cv2.waitKey(1) & 0xFF == ord('c'):
            cv2.imwrite(os.path.join(path, 'temp.jpg'), frame)
            time.sleep(2)
            break

    # When everything done, release the capture
    cap.release()
    cv2.destroyAllWindows()

    session['img_captured'] = True

    return redirect(url_for('register_student'))


@app.route('/attendance', methods=['GET', 'POST'])
@is_faculty_logged_in
def mark_attendance_1():
    std_reg = False
    std = Student.query.all()
    if len(std) > 0:
        std_reg = True
    if request.method == 'POST':
        session['lecture_no'] = request.form['lecture']
        return redirect(url_for('mark_attendance_2'))

    return render_template('mark_attendance_1.html', std_reg=std_reg)


@app.route('/attendance/fr')
@is_faculty_logged_in
def mark_attendance_2():
    return render_template('mark_attendance_2.html')


@app.route('/view_lectures_attendance/')
@is_faculty_logged_in
def view_lectures_attendance():
    lect_no = request.args.get('lecture')
    if lect_no is None:
        lect_no = 1
    # get unique lecture numbers marked by current faculty
    unique_lect_no = Attendance.query.filter_by(marked_by=session['name']).with_entities(
        Attendance.lecture_no).distinct().order_by(Attendance.lecture_no).all()
    # get the attendance for the specified lecture
    attendance = Attendance.query.filter_by(
        lecture_no=lect_no, marked_by=session['name']).all()

    return render_template('view_lecture_attendance.html', unique_lect_no=unique_lect_no, attendance=attendance)

# TODO download attendance for each lecture as marked by the teacher


@app.route('/facultydownloadcsv', defaults={'lect_no': 1})
@app.route('/facultydownloadcsv/<int:lect_no>')
@is_faculty_logged_in
def download_attendance_csv(lect_no):
    headings = 'Roll_no,Course,Lecture_no,Marked_by,Marking_date,Marking_Time\n'
    attendance = Attendance.query.filter_by(
        lecture_no=lect_no, marked_by=session['name']).all()
    rows = ''
    for a in attendance:
        rows += str(a.rollno)+','+str(a.course)+','+str(a.lecture_no)+',' + \
            (a.marked_by)+','+str(a.marked_date)+','+str(a.marked_time)+' \n'
    csv = headings+rows
    return Response(
        csv,
        mimetype="text/csv",
        headers={"Content-disposition":
                 "attachment; filename=attendance.csv"})


@app.route('/studentdownloadcsv', defaults={'course': None})
@app.route('/studentdownloadcsv/<string:course>')
@is_student_logged_in
def download_student_attendance_csv(course):
    headings = 'Roll_no,Course,Lecture_no,Marked_by,Marking_date,Marking_Time\n'
    attendance = Attendance.query.filter_by(
        rollno=session['roll_no'], course=course).all()
    rows = ''
    for a in attendance:
        rows += str(a.rollno)+','+str(a.course)+','+str(a.lecture_no)+',' + \
            (a.marked_by)+','+str(a.marked_date)+','+str(a.marked_time)+' \n'
    csv = headings+rows
    return Response(
        csv,
        mimetype="text/csv",
        headers={"Content-disposition":
                 "attachment; filename=my_attendance.csv"})


@app.route("/logout")
def logout():
    if 'std_logged_in' or 'fty_logged_in' in session:
        session.clear()
    return redirect(url_for('index'))


@app.route('/fr_attendance')
@is_faculty_logged_in
def mark_face_attendance():

    video_capture = VideoCapture(0)

    known_face_encodings = []
    known_face_names = []
    known_faces_filenames = []

    for (dirpath, dirnames, filenames) in os.walk('static/images/users'):
        known_faces_filenames.extend(filenames)
        break

    for filename in known_faces_filenames:
        face = face_recognition.load_image_file(
            'static/images/users/' + filename)
        known_face_names.append(filename[:-4])
        known_face_encodings.append(face_recognition.face_encodings(face)[0])

    face_locations = []
    face_encodings = []
    face_names = []
    process_this_frame = True

    while True:
        frame = video_capture.read()

        # Process every frame only one time
        if process_this_frame:
            # Find all the faces and face encodings in the current frame of video
            face_locations = face_recognition.face_locations(frame)
            face_encodings = face_recognition.face_encodings(
                frame, face_locations)

            # Initialize an array for the name of the detected users
            face_names = []

            # * ---------- Initialyse JSON to EXPORT --------- *
            json_to_export = {}
            flag = False
            for face_encoding in face_encodings:
                # See if the face is a match for the known face(s)
                matches = face_recognition.compare_faces(
                    known_face_encodings, face_encoding)
                roll_name = "Unknown"  # roll_name variables has roll no. and named saved. e.g. rahul-1666

                # Use the known face with the smallest distance to the new face
                face_distances = face_recognition.face_distance(
                    known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    roll_name = known_face_names[best_match_index]

                    roll = roll_name.split('-')[0]
                    # Check if the entry is is already in the DB
                    exists = Attendance.query.filter_by(rollno=roll).first()
                    # Check if the student's attendance is already marked
                    if exists:
                        is_marked_already = Attendance.query.filter(
                            Attendance.rollno == roll, Attendance.course == session['course'], Attendance.lecture_no == int(session['lecture_no'])).all()
                    # If this student is not in attendance, create an entry
                    if exists is None:
                        # Create a new row for the student:
                        attendance = Attendance(
                            rollno=roll,
                            course=session['course'],
                            lecture_no=session['lecture_no'],
                            marked_by=session['name'],
                            marked_date=datetime.date(datetime.now()),
                            marked_time=datetime.time(datetime.now())
                        )
                        db.session.add(attendance)
                        db.session.commit()

                        flag = True

                    # else if the student is already in the attendance, then check if his attendance is already marked for current lecture
                    elif len(is_marked_already) == 0:
                        # Create a new row for the student:
                        attendance = Attendance(
                            rollno=roll,
                            course=session['course'],
                            lecture_no=session['lecture_no'],
                            marked_by=session['name'],
                            marked_date=datetime.date(datetime.now()),
                            marked_time=datetime.time(datetime.now())
                        )
                        db.session.add(attendance)
                        db.session.commit()

                        flag = True
                        print('marked')

                face_names.append(roll_name)

        process_this_frame = not process_this_frame

        # Display the results
        for (top, right, bottom, left), roll_name in zip(face_locations, face_names):

            # Draw a box around the face
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)

            # Draw a label with a name below the face
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(frame, roll_name, (left + 6, bottom - 6),
                        font, 0.5, (255, 255, 255), 1)
            if flag:
                cv2.putText(frame, 'Marked', (left + 12, bottom - 12),
                            font, 0.5, (255, 255, 255), 1)

        # Display the resulting image
        cv2.imshow('Marking attendance', frame)

        # Hit 'q' on the keyboard to quit!
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release handle to the webcam
    video_capture.release()
    cv2.destroyAllWindows()

    return redirect(url_for('mark_attendance_2'))


if __name__ == '__main__':
    app.run(debug=True)
