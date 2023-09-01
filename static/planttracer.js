// Combined
// https://stackoverflow.com/questions/5448545/how-to-retrieve-get-parameters-from-javascript

function register_func() {
    let email = $('#email').val();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    let course_key = $('#course_key').val();
    if (course_key=='') {
        $('#message').html("<b>Please provide a course key</b>");
        return;
    }
    $('#message').html(`Asking to register <b>${email}</b> for course key <b>${course_key}<b>...</br>`);
    $.post('/api/register', {email:email, course_key:course_key}, function(data) {
        alert(data);
    });
};

function resend_func() {
    let email = $('#email').val();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    $('#message').html(`Asking to resend registration link for <b>${email}</b>...</br>`);
    $.post('/api/resend-link', {email:email})
        .done(function(data) {
            $('#message').html('Response: ' + data['message']);
        })
        .fail(function(xhr, status, error) {
            $('#message').html(`POST error: `+xhr['responseText']);
            console.log("xhr:",xhr);
        });
};

// https://stackoverflow.com/questions/5587973/javascript-upload-file
async function upload_movie(inp)
{
    $('#message').html(`Uploading image...`);
    console.log("upload_movie inp=",inp);
    let movieFile = inp.files[0];
    if (movieFile.fileSize > MAX_FILE_UPLOAD) {
        $('#message').html(`That file is too big to upload. Please chose a file smaller than ${MAX_FILE_UPLOAD} bytes.`);
        return;
    }
    console.log('movieFile:',movieFile);
    let formData = new FormData();
    formData.append("movie",    movieFile); // the movie itself
    formData.append("api_key",  api_key); // on the upload form
    formData.append("title",       $('#movie-title').val());
    formData.append("description", $('#movie-description').val());
    console.log('formData:',formData);

    const ctrl = new AbortController();    // timeout
    const timeoutId = setTimeout(() => ctrl.abort(), 5000);

    try {
        let r = await fetch('/api/new-movie',
                            { method:"POST", body:formData, signal: ctrl.signal });
        console.log("HTTP response code=",r);
        if (r.status!=200) {
            $('#message').html(`<i>Error uploading movie: ${r.status}</i>`);
        } else{
            const body = await r.text();
            $('#message').html(`Movie successfully uploaded: ${body}`);
            $('#movie-title').val('');
            $('#movie-description').val('');
            $('#movie-file').val('');
        }
    } catch(e) {
        console.log('Error uploading movie:',e);
        $('#message').html('Error uploading movie.');
    }
}

// For the demonstration page
function add_func() {
    let a = parseFloat($('#a').val());
    let b = parseFloat($('#b').val());
    $('#sum').html( a + b );
}

// List the movies
function list_movies() {
    console.log('list_movies');
    $('#message').html('Listing movies...');

    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch('/api/list-movies', { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            console.log("data:",data);
            if (data['error']!=false){
                $('#message').html('error: '+data['message']);
            } else {
                list_movies_data( data['movies'] );
                $('#message').html('');
            }
        })
        .catch(console.error)
    console.log('list_movies done');
}

// This is called when a checkbox in a movie table is checked. It gets the movie_id and the property and
// the old value and asks for a change. the value 'checked' is the new value, so we just send it to the server
// and then do a repaint.
function row_checkbox_clicked( e ) {
    console.log("row_checkbox_clicked e=",e);
    console.log("movie_id=", e.getAttribute('x-movie_id'));
    console.log("property=", e.getAttribute('x-property'));
    console.log("checked=", e.checked);
}

// This function is called when the edit pencil is chcked. It makes the corresponding span editable, sets up an event handler, and then selected it.
function row_pencil_clicked( e ) {
    console.log('row_pencil_clicked e=',e);
    const target = e.getAttribute('x-target');
    t = document.getElementById(target);
    console.log('target=',target,'t=',t);
    t.setAttribute('contenteditable','true');
    t.setAttribute('x-original-value', t.value); // so we can restore if the user hits escape
    t.focus();
    t.addEventListener('keydown', function(e) {
        if (e.keyCode==9 || e.keyCode==13 ){ // tab or return pressed
            console.log('escape pressed');
        } else if (e.keyCode==27){ // escape pressed
            console.log('escape pressed');
        } else {
            console.log('keycode ',e.keyCode);
        }
    });
    t.addEventListener('blur', function(e) {
        console.log('blur');
    });
}

// This is called when the editing is over and the user clicked elsewhere
function text_blur( e ) {
    console.log("text blur e=",e);
}

function text_keypress( e ) {
    console.log("keypress e=",e);
}

// todo - when lose focus, send it back
// todo - if escape, restore original

function list_movies_data( movies ) {
    // This fills in the given table with a given list
    function movies_fill_div( div, mlist ) {
        let h = "<table>";
        h += "<tr><th>id</th><th>title</th><th>description</th><th>published</th><th>delete?</th></tr>";

        // This produces the HTML for each row of the table
        function movie_html( m ) {
            // This products the HTML for each <td> that has text
            function make_td_text(id,name,text) {
                // for debugging:
                // return `<td> ${text} </td>`;
                return `<td> <span id='${id}-${name}'> ${text} </span> <span class='editor' x-target='${id}-${name}' onclick='row_pencil_clicked(this)'> ✏️  </span> </td>\n`;
            }
            // This products the HTML for each <td> that has a checkbox
            function make_td_checkbox(id,name,value) {
                // for debugging:
                // return `<td> ${name} = ${value} </td>`;
                let ch = value > 0 ? 'checked' : '';
                return `<td> <input id='${id}-${name}' x-movie_id='${m.id}' x-property='${name}' type='checkbox' ${ch} onclick='row_checkbox_clicked(this)'> </td>\n`;
            }
            return '<tr>'
                + `<td> ${m.id} </td>`
                + make_td_text(      m.id, "title", m.title) + make_td_text( m.id, "description", m.description)
                + make_td_checkbox(  m.id, "published", m.published) + make_td_checkbox( m.id, "deleted", m.deleted)
                + "</tr>\n";
        }

        if (mlist.length>0){
            mlist.forEach( m => ( h += movie_html(m) ));
        } else {
            h += '<tr><td colspan="5"><i>No movies</i></td></tr>';
        }

        h += "</table>";
        console.log("h=",h);
        div.html(h);
    }
    movies_fill_div( $('#your-published-movies'), movies.filter( m => (m['user_id']==user_id && m['published']==1)));
    movies_fill_div( $('#your-unpublished-movies'), movies.filter( m => (m['user_id']==user_id && m['published']==0 && m['deleted']==0)));
    movies_fill_div( $('#your-deleted-movies'), movies.filter( m => (m['user_id']==user_id && m['published']==0 && m['deleted']==1)));
    movies_fill_div( $('#course-movies'), movies.filter( m => (m['course_id']==user_primary_course_id)));
}

// Wire up whatever happens to be present
$( document ).ready( function() {
    $('#adder_button').click( add_func );
    $('#register_button').click( register_func );
    $('#resend_button').click( resend_func );
});
